CFLAGS += -Wall
all:	filter-env
filter-env: posix.c bmh_search.c
	$(CC) $(CFLAGS) posix.c bmh_search.c -o filter-env
clean:
	$(RM) filter-env
