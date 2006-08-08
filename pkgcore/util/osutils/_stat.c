#include <sys/stat.h>

int
isdir(char *path, int followsyms)
{
	struct stat st;
	int ret;
	if(followsyms)
		ret = stat(path, &st);
	else
		ret = lstat(path, &st);
	if(ret != 0)
		return -1;
	if S_ISDIR(st.st_mode)
		return 1;
	return 0;
}
