#!/bin/dash

# test echo

cat <<EOF > shell.sh
#!/bin/dash
name='Argo'
location="UNSW"
echo  'hello' \$2  '\$1' '\$my'  name is "\$name" "hello" 'space      space' "welcome to        \$location" \$# '\$10' : "This is the 'tenth' : \$10"
EOF
args='1 friend 3 4 5 6 7 8 9 10 11 2023'
DASH_OUTPUT=$(dash shell.sh $args)
python3 sheepy.py shell.sh > shell.py
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