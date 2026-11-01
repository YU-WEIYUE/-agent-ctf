#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {124,118,123,125,97,124,117,104,125,127,69,105,119,117,113,127,69,42,35,69,108,127,104,115,124,115,127,126,103};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-09")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^26);putchar(10);return 0;}
