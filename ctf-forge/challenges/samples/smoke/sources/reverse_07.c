#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {126,116,121,127,99,126,119,106,127,125,71,107,117,119,115,125,71,40,47,71,110,125,106,113,126,113,125,124,101};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-07")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^24);putchar(10);return 0;}
