- pdf_exe_file_shell
          
  - remove:
    
        sudo apt remove --purge shell

  - ubunut:
  
        pyinstaller --name backend_server --onedir --clean --add-data="./hello/templates:templates" --add-data="./hello/static:static" run_backend.py

  - ubunut exe install :
          
        sudo apt install ./shell_1.0.0_amd64.deb

  - windows:
    
        pyinstaller --name backend_server --onedir --clean --noconsole --add-data="./hello/templates;templates" --add-data="./hello/static;static" run_backend.py
          
  - Start electronjs:
    
        npm start
          
  - Executable file cmd for both os:
    
        npm run make


# Zoom
           ctrl+= ---> zoom in 
           
           ctrl+- ----> zoom out 
           
           ctrl+0 ---> full zoom out
           
           ctrl+r ---->reloaded 
           
           ctrl+shift+i ----> developer tool


 # Windows Location path

          C:\Users\Elanchezhian M\AppData\Local\Shell


# exe file 
          https://drive.google.com/drive/folders/1_7fj8Z0zu0_h7oQ1A9XTPjD_HD56c--I?usp=sharing
