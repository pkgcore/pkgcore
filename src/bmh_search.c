/* Boyer-Moore-Horspool algorithm for finding substrings in strings.
 * Raided from http://www.dcc.uchile.cl/~rbaeza/handbook/algs/7/713b.srch.c.html
 * apparently distributed by Addison-Wesley Publishing Co. Inc.
 */

#include <string.h>
#include <limits.h>

const char *
bmh_search(const unsigned char *pat, const unsigned char *text, int n)
{
	int i, j, m, k, skip[UCHAR_MAX + 1];

	m = strlen((char *)pat);
	if (m == 0)
		return (char *)text;

	for (k = 0; k <= UCHAR_MAX; ++k)
		skip[k] = m;
	for (k = 0; k < m - 1; k++)
		skip[pat[k]] = m - k - 1;

	for (k = m - 1; k < n; k += skip[text[k] & UCHAR_MAX]) {
		for (j = m - 1, i = k; j >= 0 && text[i] == pat[j]; --j)
			--i;
		if (j == -1)
			return (char *)(text + i + 1);
	}

	return NULL;
}
