#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {112,122,119,113,109,112,121,100,113,115,73,101,123,121,125,115,73,38,35,73,96,115,100,127,112,127,115,114,107};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-05")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^22);putchar(10);return 0;}
