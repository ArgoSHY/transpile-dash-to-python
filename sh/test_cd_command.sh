
#!/bin/dash

cat <<EOF > shell.sh
#!/bin/dash

cd ..
ls

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
    