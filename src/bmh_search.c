/* raided from http://www.dcc.uchile.cl/~rbaeza/handbook/algs/7/713b.srch.c.html
aparently distributed by Addison-Wesley Publishing Co. Inc, http://aw.com/
*/

#include <string.h>
#define MAXCHAR 256

const char *bmh_search(const unsigned char *pat, const unsigned char *text,
    int n)
{
    int i, j, m, k, skip[MAXCHAR];

    m = strlen((char *)pat);
    if (m == 0)
        return (char *)text;

    for (k=0; k<MAXCHAR; ++k)
        skip[k] = m;
    for (k=0; k<m-1; k++)
        skip[pat[k]] = m-k-1;

    for (k=m-1; k < n; k += skip[text[k] & (MAXCHAR-1)]) {
        for (j=m-1, i=k; j>=0 && text[i] == pat[j]; --j)
            --i;
        if (j == -1)
            return (char *)(text+i+1);
    }

    return NULL;
}
