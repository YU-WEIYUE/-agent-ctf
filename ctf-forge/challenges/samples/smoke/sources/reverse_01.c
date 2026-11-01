#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {116,126,115,117,105,116,125,96,117,119,77,97,127,125,121,119,77,34,35,77,100,119,96,123,116,123,119,118,111};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-01")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^18);putchar(10);return 0;}
