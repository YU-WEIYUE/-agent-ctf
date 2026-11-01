#include <stdio.h>
#include <string.h>
unsigned char cipher[] = {127,117,120,126,98,127,118,107,126,124,70,106,116,118,114,124,70,41,33,70,111,124,107,112,127,112,124,125,100};
int main(int argc,char **argv){if(argc!=2||strcmp(argv[1],"unlock-08")){puts("Find the key and pass it as argv[1]");return 1;}
for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^25);putchar(10);return 0;}
