#include <stdio.h>

void vuln()
{
    char arr[10];

    scanf("%s", arr);
}

void other_func()
{
    printf("This shit shouldn't be run");
}

int main(int argc, char const *argv[])
{
    vuln();

    printf("Run in main");
    return 0;
}
