#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {113,123,118,112,108,113,120,101,112,114,72,100,122,120,124,114,72,39,33,72,97,114,101,126,113,126,114,115,106};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-06")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^23);putchar(10);return 0;}
