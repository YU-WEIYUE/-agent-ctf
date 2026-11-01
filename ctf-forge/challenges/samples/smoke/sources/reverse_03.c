#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {114,120,117,115,111,114,123,102,115,113,75,103,121,123,127,113,75,36,39,75,98,113,102,125,114,125,113,112,105};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-03")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^20);putchar(10);return 0;}
