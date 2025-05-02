# annotator/views.py
import fitz  # PyMuPDF
import tempfile
import os
import sys # Import sys
import json
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from .forms import PDFUploadForm

# --- Constants ---
ANNOTATION_TYPES = ['tick', 'cross', 'blue_mark']
SESSION_KEY_PDF_PATH = 'pdf_path'
SESSION_KEY_ANNOTATIONS = 'annotations'
SESSION_KEY_PAGE_INFO = 'page_info'
RENDER_SCALE_FACTOR = 2.0

# --- Helper: Get Application Root (Needed for packaged paths) ---
def get_app_root():
    """Determines the app root directory, handling frozen state."""
    if getattr(sys, 'frozen', False):
        executable_path = sys.executable
        app_root = os.path.dirname(executable_path)
        return app_root
    else:
        script_path = os.path.abspath(__file__)
        app_root = os.path.dirname(os.path.dirname(script_path)) 
        return app_root


def get_session_data(request):
    """Safely get annotation data and counts from session."""
    annotations = request.session.get(SESSION_KEY_ANNOTATIONS, [])
    counts = {atype: sum(1 for ann in annotations if ann['type'] == atype) for atype in ANNOTATION_TYPES}
    return annotations, counts

def get_pdf_document(request):
    """Get the fitz document from the path stored in session."""
    pdf_path = request.session.get(SESSION_KEY_PDF_PATH)
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    try:
        doc = fitz.open(pdf_path)
        return doc
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return None


def upload_pdf(request):
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = request.FILES['pdf_file']
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                for chunk in pdf_file.chunks(): temp_pdf.write(chunk)
                temp_pdf_path = temp_pdf.name
            request.session[SESSION_KEY_PDF_PATH] = temp_pdf_path
            request.session[SESSION_KEY_ANNOTATIONS] = []
            request.session[SESSION_KEY_PAGE_INFO] = []
            try:
                doc = fitz.open(temp_pdf_path)
                page_infos = []
                for i, page in enumerate(doc):
                    rect = page.rect
                    page_infos.append({ 'page_num': i, 'orig_width': rect.width, 'orig_height': rect.height, 'render_scale': RENDER_SCALE_FACTOR })
                request.session[SESSION_KEY_PAGE_INFO] = page_infos
                doc.close()
            except Exception as e:
                 os.unlink(temp_pdf_path)
                 form.add_error('pdf_file', f'Error processing PDF: {e}')
                 return render(request, 'annotator/upload.html', {'form': form})
            return redirect('annotate_pdf')
    else:
        form = PDFUploadForm()
    return render(request, 'annotator/upload.html', {'form': form})

@require_GET
def annotate_pdf(request):
    pdf_path = request.session.get(SESSION_KEY_PDF_PATH)
    page_info = request.session.get(SESSION_KEY_PAGE_INFO)
    if not pdf_path or not page_info: return redirect('upload_pdf')
    annotations, counts = get_session_data(request)
    page_image_urls = [reverse('get_page_image', args=[info['page_num']]) for info in page_info]
    context = { 'page_count': len(page_info), 'page_image_urls': page_image_urls, 'page_info': page_info, 'annotations': annotations, 'counts': counts }
    return render(request, 'annotator/annotate.html', context)

@require_GET
def get_page_image(request, page_num):
    doc = get_pdf_document(request)
    page_info_list = request.session.get(SESSION_KEY_PAGE_INFO, [])
    if not doc or page_num >= len(doc) or page_num >= len(page_info_list): raise Http404("PDF page not found or PDF not loaded.")
    page_info = page_info_list[page_num]
    scale = page_info.get('render_scale', RENDER_SCALE_FACTOR)
    mat = fitz.Matrix(scale, scale)
    try:
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        doc.close()
        img_data = pix.tobytes("png")
        return HttpResponse(img_data, content_type="image/png")
    except Exception as e:
        if doc: doc.close()
        print(f"Error generating page image {page_num}: {e}")
        raise Http404("Error generating page image.")

@require_POST
def add_annotation(request):
    pdf_path = request.session.get(SESSION_KEY_PDF_PATH)
    page_info_list = request.session.get(SESSION_KEY_PAGE_INFO)
    if not pdf_path or not page_info_list: return JsonResponse({'status': 'error', 'message': 'No PDF loaded'}, status=400)
    try:
        data = json.loads(request.body)
        page_num = int(data['page_num'])
        img_x = float(data['x'])
        img_y = float(data['y'])
        annotation_type = data['type']
        if annotation_type not in ANNOTATION_TYPES: return JsonResponse({'status': 'error', 'message': 'Invalid annotation type'}, status=400)
        if page_num < 0 or page_num >= len(page_info_list): return JsonResponse({'status': 'error', 'message': 'Invalid page number'}, status=400)
        page_info = page_info_list[page_num]
        scale = page_info['render_scale']
        pdf_x = img_x / scale
        pdf_y = img_y / scale
        annotations = request.session.get(SESSION_KEY_ANNOTATIONS, [])
        duplicate_found = False
        for existing in annotations:
            if ( existing['page_num'] == page_num and abs(existing['pdf_x'] - pdf_x) < 1 and abs(existing['pdf_y'] - pdf_y) < 1 and existing['type'] == annotation_type ):
                annotations.remove(existing)
                duplicate_found = True
                break
        if not duplicate_found:
            new_annotation = { 'page_num': page_num, 'pdf_x': pdf_x, 'pdf_y': pdf_y, 'type': annotation_type, }
            annotations.append(new_annotation)
        request.session[SESSION_KEY_ANNOTATIONS] = annotations
        _, counts = get_session_data(request)
        return JsonResponse({ 'status': 'ok', 'counts': counts, 'action': 'removed' if duplicate_found else 'added', 'page_num': page_num, 'pdf_x': pdf_x, 'pdf_y': pdf_y, 'type': annotation_type })
    except json.JSONDecodeError: return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except (KeyError, ValueError) as e: return JsonResponse({'status': 'error', 'message': f'Missing or invalid data: {e}'}, status=400)
    except Exception as e:
        print(f"Unexpected error in add_annotation: {e}")
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred'}, status=500)


@require_GET
def download_pdf(request):
    doc = get_pdf_document(request)
    annotations, counts = get_session_data(request)

    if not doc:
        return HttpResponse("Error: PDF not found or could not be opened.", status=404)

    APP_ROOT = get_app_root() # Get the correct root path
    is_frozen = getattr(sys, 'frozen', False)

    relative_img_dir = os.path.join('static', 'annotator', 'img')

    if is_frozen:
        base_static_dir = os.path.join(APP_ROOT, '_internal', relative_img_dir)
    else:
        base_static_dir = os.path.join(APP_ROOT, 'hello', relative_img_dir) 

    # print(f"[download_pdf] Using base static dir for icons: {base_static_dir}")

    icon_paths = {
        atype: os.path.join(base_static_dir, f"{atype}.png") for atype in ANNOTATION_TYPES
    }
    icon_size = 11

    try:
        for ann in annotations:
            page_num = ann['page_num']
            if page_num < len(doc):
                page = doc[page_num]
                pdf_x = ann['pdf_x']
                pdf_y = ann['pdf_y']
                ann_type = ann['type']

                icon_path = icon_paths.get(ann_type)

                # Print path being checked
                print(f"[download_pdf] Checking icon path for '{ann_type}': {icon_path}")

                if icon_path and os.path.exists(icon_path):
                    rect = fitz.Rect(
                        pdf_x - icon_size / 2,
                        pdf_y - icon_size / 2,
                        pdf_x + icon_size / 2,
                        pdf_y + icon_size / 2
                    )
                    try:
                        print(f"[download_pdf] Inserting '{ann_type}' at ({pdf_x:.1f}, {pdf_y:.1f}) on page {page_num}")
                        page.insert_image(rect, filename=icon_path, keep_proportion=True, overlay=True)
                    except Exception as insert_err:
                        print(f"Error inserting image {icon_path} on page {page_num}: {insert_err}")
                else:
                    print(f"!!!!!!!! WARNING: Icon image NOT FOUND or path is None for type '{ann_type}' at {icon_path}")
        # --- Optional: Add counts text (Keep commented out unless needed) ---
        # if len(doc) > 0: ...

        pdf_data = doc.tobytes(garbage=4, deflate=True, clean=True)
        doc.close()

        # --- Cleanup ---
        original_temp_path = request.session.get(SESSION_KEY_PDF_PATH)
        if original_temp_path and os.path.exists(original_temp_path):
             try:
                 print(f"[download_pdf] Deleting temp file: {original_temp_path}")
                 os.unlink(original_temp_path)
                 request.session.pop(SESSION_KEY_PDF_PATH, None)
                 request.session.pop(SESSION_KEY_ANNOTATIONS, None)
                 request.session.pop(SESSION_KEY_PAGE_INFO, None)
             except OSError as e:
                 print(f"Error deleting temporary file {original_temp_path}: {e}")

        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="annotated_document.pdf"'
        return response

    except Exception as e:
        if doc: doc.close()
        print(f"Error processing PDF for download: {e}")
        original_temp_path = request.session.get(SESSION_KEY_PDF_PATH)
        if original_temp_path and os.path.exists(original_temp_path):
             try: os.unlink(original_temp_path)
             except OSError as e: print(f"Error deleting temporary file {original_temp_path} after download error: {e}")
        request.session.pop(SESSION_KEY_PDF_PATH, None)
        request.session.pop(SESSION_KEY_ANNOTATIONS, None)
        request.session.pop(SESSION_KEY_PAGE_INFO, None)

        return HttpResponse("Error processing PDF for download.", status=500)


@require_GET
def clear_pdf(request):
    annotations_key = SESSION_KEY_ANNOTATIONS
    if annotations_key in request.session:
        del request.session[annotations_key]
        print(f"Cleared session key: {annotations_key}")
    else:
        print(f"Session key '{annotations_key}' not found, nothing to clear.")
    return redirect(reverse('annotate_pdf'))