#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {115,121,116,114,110,115,122,103,114,112,74,102,120,122,126,112,74,37,33,74,99,112,103,124,115,124,112,113,104};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-04")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^21);putchar(10);return 0;}
