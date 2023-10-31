#!/usr/bin/env python3
import sys
import glob
import os
import subprocess

subprocess.run(["cat", "<<EOF", ">", "shell.sh"])
    
print(f'Exiting...')
    
sys.exit(0)
    
subprocess.run(["EOF", ])
    
args = ""
    
DASH_OUTPUT = f'{(dash shell.sh }{args})'
    
subprocess.run(["python3", "trans.py", "shell.sh", ">", "shell.py"])
    
PYTHON_OUTPUT = f'{(python3 shell.py }{args})'
    
if DASH_OUTPUT == PYTHON_OUTPUT:
    
    subprocess.run(["printf", ""\e[32mPASS\e[0m\n""])
        
    subprocess.run(["printf", ""\e[32mOutput:\n$DASH_OUTPUT\e[0m\n""])
        
else:
        
    subprocess.run(["printf", ""\e[31mFAIL\e[0m\n""])
        
    subprocess.run(["printf", ""\e[32mExpect:\n$DASH_OUTPUT\e[0m\n""])
        
    subprocess.run(["printf", ""\e[31mGot:\n$PYTHON_OUTPUT\e[0m\n""])
        
subprocess.run(["rm", "shell.sh", "shell.py"])
    