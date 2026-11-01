#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {119,125,112,118,106,119,126,99,118,116,78,98,124,126,122,116,78,33,33,78,103,116,99,120,119,120,116,117,108};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-00")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^17);putchar(10);return 0;}
