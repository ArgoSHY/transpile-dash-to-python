
#!/bin/dash

cat <<EOF > shell.sh
#!/bin/dash

value=5
if [ $value -eq 5 ]; then
    echo "The value is 5"
elif [ $value -eq 6 ]; then
    echo "The value is 6"
else
    echo "The value is neither 5 nor 6"
fi

EOF
args=''
DASH_OUTPUT=$(dash shell.sh $args)
python3 trans.py shell.sh > shell.py
PYTHON_OUTPUT=$(python3 shell.py $args)

if [ "$DASH_OUTPUT" = "$PYTHON_OUTPUT" ]; then
    printf "\e[32mPASS\e[0m\n"
    printf "\e[32mOutput:\n$DASH_OUTPUT\e[0m\n"
else
    printf "\e[31mFAIL\e[0m\n"
    printf "\e[32mExpect:\n$DASH_OUTPUT\e[0m\n"
    printf "\e[31mGot:\n$PYTHON_OUTPUT\e[0m\n"
fi

rm shell.sh shell.py
    