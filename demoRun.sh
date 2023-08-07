#!/bin/dash

INPUT_FILE=demo$1.sh

# Run the input shell script with dash
DASH_OUTPUT=$(dash $INPUT_FILE $2)

# Convert the shell script to Python using sheepy.py
python3 sheepy.py $INPUT_FILE > demo$1.py
PYTHON_OUTPUT=$(python3 demo$1.py $2)

# Compare the outputs of dash and Python
if [ "$DASH_OUTPUT" = "$PYTHON_OUTPUT" ]; then
    printf "\\e[32mPASS\\e[0m\\n"
    printf "\\e[32mOutput:\\n$DASH_OUTPUT\\e[0m\\n"
else
    printf "\\e[31mFAIL\\e[0m\\n"
    printf "\\e[32mExpect:\\n$DASH_OUTPUT\\e[0m\\n"
    printf "\\e[31mGot:\\n$PYTHON_OUTPUT\\e[0m\\n"
fi