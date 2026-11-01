#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {117,127,114,116,104,117,124,97,116,118,76,96,126,124,120,118,76,35,33,76,101,118,97,122,117,122,118,119,110};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-02")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^19);putchar(10);return 0;}
