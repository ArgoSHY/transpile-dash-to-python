#!/usr/bin/env python3
import re
import sys

class Transpiler:

    def __init__(self):
        pass

    # revised echo function, much more beautiful and useful
    def convert_echo(self, command):

        def convert_part_to_python_format(part):
            # Check if the part is wrapped in double quotes
            if part.startswith('"') and part.endswith('"'):
                part = part[1:-1]
                
                # Replacing the variables and command line arguments
                variables = re.findall(r'\$\w+|\$\{\w+\}', part)
                for var in variables:
                    if var.startswith('${'):
                        content = var[2:-1]
                        if content.isdigit():
                            part = part.replace(var, f"{{sys.argv[{content}]}}")
                        else:
                            part = part.replace(var, f"{{{content}}}")
                    elif re.match(r'\$\d+', var):
                        part = part.replace(var, f"{{sys.argv[{var[1:]}]}}")
                    else:
                        part = part.replace(var, f"{{{var[1:]}}}")
                        
            # Check if the part is wrapped in single quotes
            elif part.startswith("'") and part.endswith("'"):
                part = part[1:-1]  # Just remove the single quotes
            # For unquoted parts
            else:
                if part == '$#':
                    part = "{len(sys.argv) - 1}"  # Considering the command itself as the first argument
                else:
                    # Replacing the variables and command line arguments
                    variables = re.findall(r'\$\w+|\$\{\w+\}', part)
                    for var in variables:
                        if var.startswith('${'):
                            content = var[2:-1]
                            if content.isdigit():
                                part = part.replace(var, f"{{sys.argv[{content}]}}")
                            else:
                                part = part.replace(var, f"{{{content}}}")
                        elif re.match(r'\$\d+', var):
                            part = part.replace(var, f"{{sys.argv[{var[1:]}]}}")
                        else:
                            part = part.replace(var, f"{{{var[1:]}}}")

            if "'" in part:
                return f'f"{part}"'
            else:
                return f"f'{part}'"


        # Removing the 'echo ' part
        command = re.sub(r'^\s*echo\s+', '', command)

        # Splitting the command using the regex
        split_command = re.findall(r'".+?"|\'.+?\'|\S+', command)

        # Convert each part to Python format
        formatted_parts = [convert_part_to_python_format(part) for part in split_command]
        
        # Generating the final Python print command
        return "print(" + ", ".join(formatted_parts) + ")"

    # function before, a mess
    def convert_echo_beta(self, command):
        command = re.sub(r'^\s*echo\s+', '', command)
        n_status = False
        if command.startswith('*'): # TODO: ANY OTHER glob characters
            return 'print(" ".join(sorted(glob.glob("*"))))'
        if command.startswith('-n'):
            command = command[2:]
            n_status = True
        if command.startswith('\''):
            command = command[1:-1]
            if n_status:
                return f'print(f\'{command}\', end="")'
            return f'print(f\'{command}\')'
        if command.startswith('"'):
            command = command[1:-1]
        if command == '$@':
            return "print(sys.argv[1:])"
        words = re.split(r'(\$\w+|\s+|\$\{\w+\})', command)
        for i, word in enumerate(words):
            if word.startswith('$'):
                if word.startswith('${'):
                    content = word[2:-1]
                    if content.isdigit():
                        words[i] = '{sys.argv[' + content + ']}'
                    else:
                        words[i] = '{' + content + '}'
                elif re.match(r'\$\d+', word):
                    words[i] = f'{{sys.argv[{word[1:]}]}}'
                else:
                    words[i] = f'{{{word[1:]}}}'
            elif word.isspace():
                words[i] = ' '
        if n_status:
            return f'print(f\'{"".join(words).strip()}\', end="")'
        return f'print(f\'{"".join(words).strip()}\')'

    def convert_assignment(self, command):
        equal_sign_index = command.index('=')
        variable_name = command[:equal_sign_index].strip()
        assigned_value = command[equal_sign_index+1:].strip()
        if assigned_value.startswith('`'):
            assigned_value = assigned_value[1:-1].split()
            formatted_value = [f'str({i.replace("$", "")})' if i.startswith("$") else f'"{i}"' for i in assigned_value]
            escape_value = [i.replace('\\','') if '\\' in i else i for i in formatted_value]
            return f'''{variable_name} = subprocess.run([{", ".join(escape_value)}], text=True, stdout=subprocess.PIPE).stdout.strip()'''
        if assigned_value.startswith('"') or assigned_value.startswith("'"):
            assigned_value = assigned_value[1:-1]
        if '$' in assigned_value:
            words = re.split(r'(\$\w+|\$\{\w+\})', assigned_value)
            for i, word in enumerate(words):
                if word.startswith('$'):
                    if word.startswith('${'):
                        # Check if the content of {} can be parsed as an integer
                        content = word[2:-1]
                        if content.isdigit():
                            words[i] = '{sys.argv[' + content + ']}'
                        else:
                            words[i] = '{' + content + '}'
                    elif re.match(r'\$\d+', word):
                        words[i] = f'{{sys.argv[{word[1:]}]}}'
                    else:
                        words[i] = f'{{{word[1:]}}}'
            assigned_value = f'f\'{"".join(words)}\''
        else:
            assigned_value = f'"{assigned_value}"'
        return f'{variable_name} = {assigned_value}'

    def convert_comment(self, command):
        return command.strip()

    def convert_command(self, command):
    # Use regular expression to split the command into name and arguments
        match = re.search(r'(\s*)(\w+)(.*)', command)
        name = match.group(2)
        arguments = match.group(3).strip().split()
        
        arguments_list = []
        for arg in arguments:
            if arg == '$@' or arg == '"$@"':
                arguments_list.append('*sys.argv[1:]')
                continue
            
            if arg.startswith('"$') and arg.endswith('"'):
                arguments_list.append(arg[2:-1])  # strip surrounding quotes and $
            elif arg.startswith('$'):
                arguments_list.append(arg[1:])
            else:
                arguments_list.append(f'"{arg}"')

        arguments_str = ', '.join(arguments_list)

        return f'subprocess.run(["{name}", {arguments_str}])'

    def convert_cd(self, command):
        _, path = command.split(" ", 1)
        return f"os.chdir('{path}')"

    def convert_for(self, command):
        command = re.sub(r'\bdo\b', '', command)
        command = re.sub(r'\bdone\b', '', command)
        command = re.sub(r';\s*$', '', command)
        parts = command.split()
        variable_name = parts[1]
        iterable = parts[3:]
        if '*' in str(iterable): # TODO: ANY OTHER glob characters
            iterable = "sorted(glob.glob('" + iterable[0] + "'))"
        else:
            iterable = str(iterable)
        return f"for {variable_name} in {iterable}:\n"

    # This has 2 output
    def convert_if(self, command):
        command = re.sub(r'\bthen\b', '', command)
        command = re.sub(r'\bfi\b', '', command)
        command = re.sub(r';\s*$', '', command)
        _, condition = command.split('if')
        condition, condition2 = self.convert_test(condition)
        return f'if {condition}', condition2
    
    # This has 2 output
    def convert_elif(self, command):
        command = re.sub(r'\bthen\b', '', command)
        command = re.sub(r'\bfi\b', '', command)
        command = re.sub(r';\s*$', '', command)
        _, condition = command.split('elif')
        condition, condition2 = self.convert_test(condition)
        return f'elif {condition}', condition2
    
    def convert_else(self, command):
        return 'else:'
    
    # This has 2 output
    def convert_while(self, command):
        command = re.sub(r'\bdo\b', '', command)
        command = re.sub(r'\bdone\b', '', command)
        command = re.sub(r';\s*$', '', command)
        _, condition = command.split('while')
        condition, condition2 = self.convert_test(condition)
        return f'while {condition}', condition2

    # This has 2 output to while if elif to num the number
    def convert_test(self, command):
        """Translate the test condition based on numeric or non-numeric handling."""

        def handle_numeric(s):
            # TODO: USE THIS FUNC IN THE WHOLE CLASS
            """Handle strings that represent numbers or numeric variables"""
            s = s.strip()
            # Handle script arguments like $1, $2,... and "$1", "$2",...
            if s == '"$#"' or s == '$#':
                return "len(sys.argv) - 1"
            elif s.startswith('$') and s[1:].isdigit():
                return f"sys.argv[{s[1:]}]"
            elif s.startswith('"$') and s.endswith('"') and s[2:-1].isdigit():
                return f"sys.argv[{s[2:-1]}]"
            # If string starts with $, it's a variable
            elif s.startswith('$'):
                return s[1:]
            # If string represents a number, return it as is
            elif s.isdigit():
                return s
            # If string is enclosed in quotes and is a number, return the number
            elif s.startswith('"') and s.endswith('"') and s[1:-1].isdigit():
                return s[1:-1]
            # If string starts with "$" and is a variable, it's a variable without $ sign
            elif s.startswith('"$') and s.endswith('"'):
                return s[2:-1]
            # If string is not enclosed in quotes and not a number, it's a variable
            else:
                return s

        def handle_non_numeric(s):
            # TODO: USE THIS FUNC IN THE WHOLE CLASS
            """Updated handle_non_numeric function based on user's specifications."""
            s = s.strip()
            
            # Handle script arguments like $1, $2,... and "$1", "$2",...
            if s.startswith('$') and s[1:].isdigit():
                return f"sys.argv[{s[1:]}]"
            elif s.startswith('"$') and s.endswith('"') and s[2:-1].isdigit():
                return f"sys.argv[{s[2:-1]}]"
            # If string starts with "$" and is a variable, it's a variable without $ sign
            elif s.startswith('"$') and s.endswith('"'):
                return s[2:-1]
            # If string starts with $, it's a variable
            elif s.startswith('$'):
                return s[1:]
            # If string starts with '$' and is a variable, it remains unchanged
            elif s.startswith("'$") and s.endswith("'"):
                return s
            # If string is enclosed in quotes, it's a direct string
            elif s.startswith('"') and s.endswith('"'):
                return f"'{s[1:-1]}'"
            elif s.startswith("'") and s.endswith("'"):
                return f"'{s[1:-1]}'"
            # If string is not enclosed in quotes and not a number, it's a variable or string
            else:
                return f"'{s}'"
            
        # Function to check the num
        def is_number(s1, s2, op):
            if s1.isdigit():
                s1_result, s1_is_num = s1, True
            elif s1 == 'len(sys.argv) - 1':
                s1_result, s1_is_num = f"len(sys.argv) - 1", True
            else:
                s1_result, s1_is_num = f"int({s1})", False

            if s2.isdigit():
                s2_result, s2_is_num = s2, True
            elif s2 == 'len(sys.argv) - 1':
                s2_result, s2_is_num = f"len(sys.argv) - 1", True
            else:
                s2_result, s2_is_num = f"int({s2})", False

            if s1_is_num and s2_is_num:
                return f"{s1_result} {op} {s2_result}:", ''
            elif s1_is_num and not s2_is_num:
                return f"{s1_result} {op} {s2_result}:", f"{s2}={s2_result}"
            elif not s1_is_num and s2_is_num:
                return f"{s1_result} {op} {s2_result}:", f"{s1}={s1_result}"
            else:
                return f"{s1_result} {op} {s2_result}:", f"{s1}, {s2} = {s1_result}, {s2_result}"

        if 'test' in command:
            command = command.split('test')[1].strip()
        elif '[' in command:
            command = command.split('[')[1].replace(']','').strip()

        # Check for file existence and readability
        if '-r' in command:
            filepath = command.split('-r')[1].strip()
            return f"os.access({handle_non_numeric(filepath)}, os.R_OK):", ''

        # Check for directory
        elif '-d' in command:
            filepath = command.split('-d')[1].strip()
            return f"os.path.isdir({handle_non_numeric(filepath)}):", ''

        # Check for string equality
        elif ' =' in command:
            parts = command.split('=')
            return f"{handle_non_numeric(parts[0].strip())} == {handle_non_numeric(parts[1].strip())}:", ''

        # Check for string inequality
        elif '!=' in command:
            parts = command.split('!=')
            return f"{handle_non_numeric(parts[0].strip())} != {handle_non_numeric(parts[1].strip())}:", ''

        # Numeric comparisons
        elif '-eq' in command:
            op = '=='
            parts = command.split('-eq')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)
            # return f"{handle_numeric(parts[0].strip())} == {handle_numeric(parts[1].strip())}"
        elif '-ne' in command:
            op = '!='
            parts = command.split('-ne')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)
        elif '-gt' in command:
            op = '>'
            parts = command.split('-gt')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)
        elif '-ge' in command:
            op = '>='
            parts = command.split('-ge')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)
        elif '-lt' in command:
            op = '<'
            parts = command.split('-lt')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)
        elif '-le' in command:
            op = '<='
            parts = command.split('-le')
            return is_number(handle_numeric(parts[0].strip()), handle_numeric(parts[1].strip()), op)

        # Check for string length zero
        elif '-z' in command:
            string = command.split('-z')[1].strip()
            return f"len({handle_non_numeric(string)}) == 0:", ''
        elif '-s' in command:
            filepath = command.split('-s')[1].strip()
            return f"os.path.getsize({handle_non_numeric(filepath)}) > 0:", ''
        # File exists
        elif '-f' in command:
            filepath = command.split('-f')[1].strip()
            return f"os.path.isfile({handle_non_numeric(filepath)}):", ''
        # File is executable
        elif '-x' in command:
            filepath = command.split('-x')[1].strip()
            return f"os.access({handle_non_numeric(filepath)}, os.X_OK):", ''
        # File is writable
        elif '-w' in command:
            filepath = command.split('-w')[1].strip()
            return f"os.access({handle_non_numeric(filepath)}, os.W_OK):", ''
        # File is a symbolic link
        elif '-h' in command or '-L' in command:
            filepath = command.split('-h')[1].strip() if '-h' in command else command.split('-L')[1].strip()
            return f"os.path.islink({handle_non_numeric(filepath)}):", ''
        # File's group ID matches the effective group ID
        elif '-G' in command:
            filepath = command.split('-G')[1].strip()
            return f"os.stat({handle_non_numeric(filepath)}).st_gid == os.getgid():", ''
        # File's user ID matches the effective user ID
        elif '-O' in command:
            filepath = command.split('-O')[1].strip()
            return f"os.stat({handle_non_numeric(filepath)}).st_uid == os.getuid():", ''
        # Unsupported condition or
        # TODO: Add more conditions as needed
        else:
            return f"# Unsupported test condition: {command}"

    def convert_exit(self, command):
        command = command.split(' ')[1]
        exit_code = f'{command}' if command else '0'
        return f'sys.exit({exit_code})'

    def convert_read(self, command):
        variable_name = command.split(' ')[-1]
        python_command = f'{variable_name} = input()'
        return python_command
    
    def split_comment_from_command(self, line):
        """
        Splits the command and the comment from a given line.
        Returns the command and the comment.
        """
        in_single_quote = False
        in_double_quote = False

        # Iterate through the characters of the line to find the position of the first # outside of quotes
        idx = 0
        while idx < len(line):
            char = line[idx]
            
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == '#' and not in_single_quote and not in_double_quote:
                # Check if the # is preceded by $, indicating it's not a comment
                if idx > 0 and line[idx - 1] == '$':
                    idx += 1
                    continue
                # Return command and comment as separate entities
                return line[:idx].strip(), line[idx+1:].strip()
            
            idx += 1
            
        # If there's no comment, return the whole line as command and None as comment
        return line.strip(), ''

    def remove_blank(self, script):
        lines = script.split('\n')
        new_lines = []
        is_previous_line_blank = False

        for line in lines:
            is_current_line_blank = not line.strip()  # Check if the line is blank or contains only whitespace

            if is_current_line_blank and is_previous_line_blank:
                continue  # Skip this line if the previous line was also blank
            new_lines.append(line)
            is_previous_line_blank = is_current_line_blank
        return '\n'.join(new_lines)


    def transpile(self, dash_script):
        python_script = "#!/usr/bin/env python3\n"
        python_script += "import sys\nimport glob\nimport os\nimport subprocess\n\n"
        commands = dash_script.split('\n')
        syn_status = 0
        for command in commands:
            python_command = ''
            if command.startswith('#!/bin/dash'):
                continue
            indent = '    '  * syn_status
            indent_min = '    ' * (syn_status - 1)
            indent_max = '    ' * (syn_status + 1)
            command, comment = self.split_comment_from_command(command)
            command = command.strip()
            comment = comment.strip()
            next = ''
            if command.startswith('#!/bin/dash'):
                continue
            elif re.search(r'(\s*)echo (.*)', command):
                python_command = self.convert_echo(command)
            elif re.search(r'(\s*)elif (.*)', command):
                python_command, next = self.convert_elif(command)
            elif re.search(r'(\s*)if (.*)', command):
                python_command, next = self.convert_if(command)
                syn_status += 1
            elif re.search(r'(\s*)while (.*)', command):
                python_command, next  = self.convert_while(command)
                syn_status += 1
            elif re.search(r'(\s*)else(.*)', command):
                python_command = self.convert_else(command)
            elif '=' in command and 'test' not in command:
                python_command = self.convert_assignment(command)
            elif re.search(r'(\s*)cd (.*)', command):
                python_command = self.convert_cd(command)
            elif re.search(r'(\s*)for (.*)', command):
                python_command = self.convert_for(command)
                syn_status += 1
            elif re.search(r'(\s*)read (.*)', command):
                python_command = self.convert_read(command)
            elif re.search(r'(\s*)exit (.*)', command):
                python_command = self.convert_exit(command)
            elif syn_status and (command.strip() == 'done' or command.strip() == 'fi'):
                syn_status -= 1
                continue
            elif command.strip() == 'then':
                continue
            elif re.search(r'(\s*)(\w+)(.*)', command) and command.split()[0] != 'do':  # Change to match any command
                python_command = self.convert_command(command)
            
            if comment:
                python_command += f'  # {self.convert_comment(comment)}'

            if command.startswith('else') or command.startswith('elif'):
                python_script += indent_min + python_command + "\n"
                python_script += indent_max + next + "\n"
            else:
                python_script += indent + python_command + "\n"
                python_script += indent_max + next + "\n"
        return self.remove_blank(python_script)


if __name__ == "__main__":
    transpiler = Transpiler()
    with open(sys.argv[1], "r") as f:
        dash_script = f.read()
    python_script = transpiler.transpile(dash_script)
    print(python_script)
