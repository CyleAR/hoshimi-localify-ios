/* GitHub Release translation-data updater. Included by hook.c after image_hook.h. */
#define UPDATE_API_URL "https://api.github.com/repos/CyleAR/ipr-translation-data-ko/releases/latest"
#define UPDATE_UTF8 0x08000100u

static int update_started;
static char update_current_version[128];
static char update_data_root[4096];

static int update_read_setting(const char *name, char *output, size_t capacity) {
  typedef void *(*Create)(void *, const char *, uint32_t);
  typedef void *(*Copy)(void *, void *);
  typedef uintptr_t (*TypeID)(const void *);
  typedef uintptr_t (*StringTypeID)(void);
  typedef uint8_t (*GetCString)(void *, char *, intptr_t, uint32_t);
  typedef void (*Release)(void *);
  void *cf = dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", RTLD_NOW);
  if (!cf) return 0;
  Create create = (Create)dlsym(cf, "CFStringCreateWithCString");
  Copy copy = (Copy)dlsym(cf, "CFPreferencesCopyAppValue");
  TypeID type = (TypeID)dlsym(cf, "CFGetTypeID");
  StringTypeID string_type = (StringTypeID)dlsym(cf, "CFStringGetTypeID");
  GetCString get = (GetCString)dlsym(cf, "CFStringGetCString");
  Release release = (Release)dlsym(cf, "CFRelease");
  void **app = (void **)dlsym(cf, "kCFPreferencesCurrentApplication");
  int ok = 0;
  if (create && copy && type && string_type && get && release && app && *app) {
    void *key = create(0, name, UPDATE_UTF8);
    void *value = key ? copy(key, *app) : 0;
    if (value && type(value) == string_type())
      ok = get(value, output, (intptr_t)capacity, UPDATE_UTF8) != 0;
    if (value) release(value);
    if (key) release(key);
  }
  dlclose(cf);
  return ok;
}

static void update_write_setting(const char *name, const char *text) {
  typedef void *(*Create)(void *, const char *, uint32_t);
  typedef void (*Set)(void *, void *, void *);
  typedef uint8_t (*Sync)(void *);
  typedef void (*Release)(void *);
  void *cf = dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", RTLD_NOW);
  if (!cf) return;
  Create create = (Create)dlsym(cf, "CFStringCreateWithCString");
  Set set = (Set)dlsym(cf, "CFPreferencesSetAppValue");
  Sync sync = (Sync)dlsym(cf, "CFPreferencesAppSynchronize");
  Release release = (Release)dlsym(cf, "CFRelease");
  void **app = (void **)dlsym(cf, "kCFPreferencesCurrentApplication");
  if (create && set && sync && release && app && *app) {
    void *key = create(0, name, UPDATE_UTF8);
    void *value = create(0, text, UPDATE_UTF8);
    if (key && value) {
      set(key, value, *app);
      sync(*app);
    }
    if (value) release(value);
    if (key) release(key);
  }
  dlclose(cf);
}

static int update_safe_version(const char *value) {
  size_t length = value ? strlen(value) : 0;
  if (!length || length >= 96) return 0;
  if (!strcmp(value, ".") || !strcmp(value, "..")) return 0;
  for (size_t i = 0; i < length; ++i) {
    char c = value[i];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.'))
      return 0;
  }
  return 1;
}

/* Resolve directory traversal APIs at runtime so the SDK-free build does not
 * depend on Darwin's readdir symbol variant.  The layout matches arm64 Darwin;
 * only d_name is inspected. */
typedef struct UpdateDir UpdateDir;
typedef struct UpdateDirEntry {
  uint64_t d_ino;
  uint64_t d_seekoff;
  uint16_t d_reclen;
  uint16_t d_namlen;
  uint8_t d_type;
  char d_name[1024];
} UpdateDirEntry;
typedef UpdateDir *(*UpdateOpenDir)(const char *);
typedef UpdateDirEntry *(*UpdateReadDir)(UpdateDir *);
typedef int (*UpdateCloseDir)(UpdateDir *);

typedef struct UpdateDirApi {
  void *handle;
  UpdateOpenDir open;
  UpdateReadDir read;
  UpdateCloseDir close;
} UpdateDirApi;

static int update_open_dir_api(UpdateDirApi *api) {
  memset(api, 0, sizeof(*api));
  api->handle = dlopen("/usr/lib/libSystem.B.dylib", RTLD_NOW);
  if (!api->handle) return 0;
  api->open = (UpdateOpenDir)dlsym(api->handle, "opendir");
  api->read = (UpdateReadDir)dlsym(api->handle, "readdir");
  if (!api->read)
    api->read = (UpdateReadDir)dlsym(api->handle, "readdir$INODE64");
  api->close = (UpdateCloseDir)dlsym(api->handle, "closedir");
  if (api->open && api->read && api->close) return 1;
  dlclose(api->handle);
  memset(api, 0, sizeof(*api));
  return 0;
}

static int update_remove_tree(UpdateDirApi *api, const char *path,
                              unsigned int depth) {
  if (!api || !path || !*path || depth > 32) return 0;
  /* Files, symlinks and empty directories are removed here.  In particular,
   * removing a symlink before opendir() prevents traversal outside versions/. */
  if (remove(path) == 0) return 1;
  UpdateDir *directory = api->open(path);
  if (!directory) return 0;
  int ok = 1;
  UpdateDirEntry *entry;
  while ((entry = api->read(directory))) {
    const char *name = entry->d_name;
    if (!strcmp(name, ".") || !strcmp(name, "..")) continue;
    char child[4096];
    int length = snprintf(child, sizeof(child), "%s/%s", path, name);
    if (length <= 0 || (size_t)length >= sizeof(child)) {
      ok = 0;
      continue;
    }
    if (!update_remove_tree(api, child, depth + 1))
      ok = 0;
  }
  api->close(directory);
  if (remove(path) != 0) ok = 0;
  return ok;
}

static void update_cleanup_versions(const char *home, const char *selected) {
  if (!home || !update_safe_version(selected)) return;
  char versions_root[4096];
  int root_length = snprintf(
      versions_root, sizeof(versions_root),
      "%s/Library/Application Support/HoshimiLocalAPI/versions", home);
  if (root_length <= 0 || (size_t)root_length >= sizeof(versions_root)) return;

  UpdateDirApi api;
  if (!update_open_dir_api(&api)) {
    record("UPDATE CLEANUP SKIP: directory API unavailable");
    return;
  }
  UpdateDir *directory = api.open(versions_root);
  if (!directory) {
    dlclose(api.handle);
    return;
  }
  unsigned int removed = 0, failed = 0, skipped = 0;
  UpdateDirEntry *entry;
  while ((entry = api.read(directory))) {
    const char *name = entry->d_name;
    if (!strcmp(name, ".") || !strcmp(name, "..") ||
        !strcmp(name, selected))
      continue;
    /* Leave unexpected entries alone.  The updater only owns directories
     * whose names pass the same release-version validation used on download. */
    if (!update_safe_version(name)) {
      ++skipped;
      continue;
    }
    char old_root[4096];
    int length = snprintf(old_root, sizeof(old_root), "%s/%s", versions_root,
                          name);
    if (length <= 0 || (size_t)length >= sizeof(old_root)) {
      ++failed;
      continue;
    }
    if (update_remove_tree(&api, old_root, 0))
      ++removed;
    else
      ++failed;
  }
  api.close(directory);
  dlclose(api.handle);
  if (removed || failed || skipped)
    record("UPDATE CLEANUP: active=%s removed=%u failed=%u skipped=%u",
           selected, removed, failed, skipped);
}

static int update_mkdirs(const char *path) {
  size_t length = strlen(path);
  if (!length || length >= 4096) return 0;
  char copy[4096];
  memcpy(copy, path, length + 1);
  for (size_t i = 1; i < length; ++i) {
    if (copy[i] != '/') continue;
    copy[i] = 0;
    mkdir(copy, 0755);
    copy[i] = '/';
  }
  mkdir(copy, 0755);
  return 1;
}

static int update_read_text(const char *path, char *output, size_t capacity) {
  FILE *file = fopen(path, "rb");
  if (!file) return 0;
  size_t read = fread(output, 1, capacity - 1, file);
  int extra = fseek(file, 0, SEEK_END) ? 1 : ftell(file) > (long)read;
  fclose(file);
  if (extra) return 0;
  while (read && (output[read - 1] == '\r' || output[read - 1] == '\n' ||
                  output[read - 1] == ' ' || output[read - 1] == '\t'))
    --read;
  output[read] = 0;
  return read != 0;
}

static int update_file_exists(const char *path) {
  FILE *file = fopen(path, "rb");
  if (!file) return 0;
  fclose(file);
  return 1;
}

static int update_copy_path(char *output, size_t capacity, const char *root,
                            const char *suffix) {
  int length = snprintf(output, capacity, "%s/%s", root, suffix);
  return length > 0 && (size_t)length < capacity;
}

static int update_validate_root(const char *root, const char *expected,
                                int require_complete) {
  static const char *required[] = {"version.txt",
                                   "ios-data/localization.bin",
                                   "ios-data/master.bin", "ios-data/generic.bin",
                                   "ios-data/phone.bin"};
  char path[4096], version[128];
  if (require_complete &&
      (!update_copy_path(path, sizeof(path), root, ".complete") ||
       !update_file_exists(path)))
    return 0;
  for (size_t i = 0; i < sizeof(required) / sizeof(required[0]); ++i)
    if (!update_copy_path(path, sizeof(path), root, required[i]) ||
        !update_file_exists(path))
      return 0;
  if (!update_copy_path(path, sizeof(path), root, "version.txt") ||
      !update_read_text(path, version, sizeof(version)))
    return 0;
  return !expected || !strcmp(version, expected);
}

static void update_set_paths(const char *root, int remote) {
  update_copy_path(image_root, sizeof(image_root), root,
                   "local-files/resource/img");
  update_copy_path(adv_root, sizeof(adv_root), root,
                   "local-files/resource/adv");
  update_copy_path(master_path, sizeof(master_path), root,
                   remote ? "ios-data/master.bin" : "master.bin");
  update_copy_path(generic_path, sizeof(generic_path), root,
                   remote ? "ios-data/generic.bin" : "generic.bin");
  update_copy_path(phone_path, sizeof(phone_path), root,
                   remote ? "ios-data/phone.bin" : "phone.bin");
  update_copy_path(localization_path, sizeof(localization_path), root,
                   remote ? "ios-data/localization.bin" : "localization.bin");
}

static void update_select_data_root(const char *embedded_root) {
  update_set_paths(embedded_root, 0);
  char embedded_version_path[4096];
  if (update_copy_path(embedded_version_path, sizeof(embedded_version_path),
                       embedded_root, "version.txt"))
    update_read_text(embedded_version_path, update_current_version,
                     sizeof(update_current_version));
  const char *home = getenv("HOME");
  char selected[128] = {0};
  if (api_assets_enabled && home &&
      update_read_setting("activeTranslationDataVersion", selected,
                          sizeof(selected)) &&
      update_safe_version(selected)) {
    int n = snprintf(update_data_root, sizeof(update_data_root),
                     "%s/Library/Application Support/HoshimiLocalAPI/versions/%s",
                     home, selected);
    if (n > 0 && (size_t)n < sizeof(update_data_root) &&
        update_validate_root(update_data_root, selected, 1)) {
      update_set_paths(update_data_root, 1);
      memcpy(update_current_version, selected, strlen(selected) + 1);
      record("UPDATE ACTIVE: version=%s root=%s", selected, update_data_root);
      char stale_download[4096];
      if (update_copy_path(stale_download, sizeof(stale_download),
                           update_data_root, "remote.zip.tmp"))
        remove(stale_download);
      /* Cleanup happens only after the downloaded version survives a restart
       * and becomes the validated active root.  This avoids deleting files a
       * previous process may still have been reading lazily. */
      update_cleanup_versions(home, selected);
    } else {
      update_data_root[0] = 0;
      record("UPDATE FALLBACK: active data invalid; using embedded data");
    }
  }
  update_write_setting("currentTranslationDataVersion",
                       update_current_version[0] ? update_current_version : "알 수 없음");
}

static uint16_t update_le16(const unsigned char *p) {
  return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}
static uint32_t update_le32(const unsigned char *p) {
  return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 |
         (uint32_t)p[3] << 24;
}

typedef struct UpdateZStream {
  unsigned char *next_in;
  unsigned int avail_in;
  unsigned long total_in;
  unsigned char *next_out;
  unsigned int avail_out;
  unsigned long total_out;
  char *msg;
  void *state;
  void *zalloc;
  void *zfree;
  void *opaque;
  int data_type;
  unsigned long adler;
  unsigned long reserved;
} UpdateZStream;

static int update_inflate(const unsigned char *input, size_t input_size,
                          unsigned char *output, size_t output_size) {
  typedef const char *(*Version)(void);
  typedef int (*Init)(UpdateZStream *, int, const char *, int);
  typedef int (*Inflate)(UpdateZStream *, int);
  typedef int (*End)(UpdateZStream *);
  void *zlib = dlopen("/usr/lib/libz.1.dylib", RTLD_NOW);
  if (!zlib) zlib = dlopen("/usr/lib/libz.dylib", RTLD_NOW);
  if (!zlib || input_size > 0xffffffffu || output_size > 0xffffffffu) {
    if (zlib) dlclose(zlib);
    return 0;
  }
  Version version = (Version)dlsym(zlib, "zlibVersion");
  Init init = (Init)dlsym(zlib, "inflateInit2_");
  Inflate inflate = (Inflate)dlsym(zlib, "inflate");
  End end = (End)dlsym(zlib, "inflateEnd");
  UpdateZStream stream;
  memset(&stream, 0, sizeof(stream));
  stream.next_in = (unsigned char *)input;
  stream.avail_in = (unsigned int)input_size;
  stream.next_out = output;
  stream.avail_out = (unsigned int)output_size;
  int ok = version && init && inflate && end &&
           init(&stream, -15, version(), (int)sizeof(stream)) == 0 &&
           inflate(&stream, 4) == 1 && stream.total_out == output_size;
  if (stream.state && end) end(&stream);
  dlclose(zlib);
  return ok;
}

static int update_zip_safe_name(const char *name) {
  if (!name[0] || name[0] == '/' || name[0] == '\\' || strstr(name, "../") ||
      strstr(name, "/..") || strstr(name, "\\") || strstr(name, ":"))
    return 0;
  return 1;
}

static int update_zip_wanted(const char *name) {
  return !strcmp(name, "version.txt") || !strncmp(name, "ios-data/", 9) ||
         !strncmp(name, "local-files/resource/adv/", 25) ||
         !strncmp(name, "local-files/resource/img/", 25);
}

static int update_extract_entry(FILE *zip, const char *root, const char *name,
                                uint16_t method, uint32_t compressed,
                                uint32_t uncompressed, uint32_t local_offset) {
  if (!update_zip_safe_name(name) || !update_zip_wanted(name)) return 1;
  if (name[strlen(name) - 1] == '/') return 1;
  if (uncompressed > 128u * 1024u * 1024u || compressed > 128u * 1024u * 1024u)
    return 0;
  unsigned char local[30];
  if (fseek(zip, (long)local_offset, SEEK_SET) || fread(local, 1, sizeof(local), zip) != sizeof(local) ||
      update_le32(local) != 0x04034b50u)
    return 0;
  uint16_t name_length = update_le16(local + 26), extra_length = update_le16(local + 28);
  long data_offset = (long)local_offset + 30 + name_length + extra_length;
  if (fseek(zip, data_offset, SEEK_SET)) return 0;
  unsigned char *packed = compressed ? malloc(compressed) : 0;
  unsigned char *plain = uncompressed ? malloc(uncompressed) : malloc(1);
  if ((compressed && !packed) || !plain) {
    free(packed); free(plain); return 0;
  }
  int ok = (!compressed || fread(packed, 1, compressed, zip) == compressed);
  if (ok && !uncompressed)
    ok = 1;
  else if (ok && method == 0)
    ok = compressed == uncompressed && (!uncompressed || (memcpy(plain, packed, uncompressed), 1));
  else if (ok && method == 8)
    ok = update_inflate(packed, compressed, plain, uncompressed);
  else
    ok = 0;
  char output_path[4608];
  int n = snprintf(output_path, sizeof(output_path), "%s/%s", root, name);
  if (ok && n > 0 && (size_t)n < sizeof(output_path)) {
    char parent[4608];
    memcpy(parent, output_path, (size_t)n + 1);
    char *slash = parent + n;
    while (slash > parent && *slash != '/') --slash;
    if (slash > parent) { *slash = 0; update_mkdirs(parent); }
    FILE *out = fopen(output_path, "wb");
    ok = out && (!uncompressed || fwrite(plain, 1, uncompressed, out) == uncompressed);
    if (out) fclose(out);
  } else ok = 0;
  free(packed); free(plain);
  return ok;
}

static int update_extract_zip(const char *zip_path, const char *root) {
  FILE *zip = fopen(zip_path, "rb");
  if (!zip || fseek(zip, 0, SEEK_END)) { if (zip) fclose(zip); return 0; }
  long length = ftell(zip);
  if (length < 22) { fclose(zip); return 0; }
  size_t tail_size = (size_t)(length < 65557 ? length : 65557);
  unsigned char *tail = malloc(tail_size);
  if (!tail || fseek(zip, length - (long)tail_size, SEEK_SET) ||
      fread(tail, 1, tail_size, zip) != tail_size) {
    free(tail); fclose(zip); return 0;
  }
  size_t eocd = tail_size;
  while (eocd >= 22) {
    --eocd;
    if (update_le32(tail + eocd) == 0x06054b50u) break;
  }
  if (eocd + 22 > tail_size) { free(tail); fclose(zip); return 0; }
  uint16_t entries = update_le16(tail + eocd + 10);
  uint32_t central_offset = update_le32(tail + eocd + 16);
  free(tail);
  if (!entries || fseek(zip, (long)central_offset, SEEK_SET)) { fclose(zip); return 0; }
  update_mkdirs(root);
  int extracted = 0, ok = 1;
  for (uint16_t i = 0; i < entries && ok; ++i) {
    unsigned char central[46];
    if (fread(central, 1, sizeof(central), zip) != sizeof(central) ||
        update_le32(central) != 0x02014b50u) { ok = 0; break; }
    uint16_t method = update_le16(central + 10);
    uint32_t compressed = update_le32(central + 20), uncompressed = update_le32(central + 24);
    uint16_t name_length = update_le16(central + 28), extra_length = update_le16(central + 30);
    uint16_t comment_length = update_le16(central + 32);
    uint32_t local_offset = update_le32(central + 42);
    if (!name_length || name_length >= 4096) { ok = 0; break; }
    char name[4096];
    if (fread(name, 1, name_length, zip) != name_length) { ok = 0; break; }
    name[name_length] = 0;
    long next = ftell(zip) + extra_length + comment_length;
    int wanted = update_zip_wanted(name) && name[name_length - 1] != '/';
    if (!update_extract_entry(zip, root, name, method, compressed, uncompressed, local_offset))
      ok = 0;
    else if (wanted)
      ++extracted;
    if (ok && fseek(zip, next, SEEK_SET)) ok = 0;
  }
  fclose(zip);
  return ok && extracted >= 5;
}

static int update_http_get(const char *url, const char *output_path,
                           char **memory, size_t *memory_size) {
  typedef void *(*StringCreate)(void *, const char *, uint32_t);
  typedef void *(*UrlCreate)(void *, void *, void *);
  typedef void *(*MessageCreate)(void *, void *, void *, void *);
  typedef void (*SetHeader)(void *, void *, void *);
  typedef void *(*StreamCreate)(void *, void *);
  typedef uint8_t (*StreamProperty)(void *, void *, void *);
  typedef uint8_t (*StreamOpen)(void *);
  typedef intptr_t (*StreamRead)(void *, unsigned char *, intptr_t);
  typedef void (*StreamClose)(void *);
  typedef void (*Release)(void *);
  void *cf = dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", RTLD_NOW);
  void *net = dlopen("/System/Library/Frameworks/CFNetwork.framework/CFNetwork", RTLD_NOW);
  if (!cf || !net) { if (cf) dlclose(cf); if (net) dlclose(net); return 0; }
  StringCreate string_create = (StringCreate)dlsym(cf, "CFStringCreateWithCString");
  UrlCreate url_create = (UrlCreate)dlsym(cf, "CFURLCreateWithString");
  StreamProperty set_property = (StreamProperty)dlsym(cf, "CFReadStreamSetProperty");
  StreamOpen open = (StreamOpen)dlsym(cf, "CFReadStreamOpen");
  StreamRead read = (StreamRead)dlsym(cf, "CFReadStreamRead");
  StreamClose close = (StreamClose)dlsym(cf, "CFReadStreamClose");
  Release release = (Release)dlsym(cf, "CFRelease");
  MessageCreate message_create = (MessageCreate)dlsym(net, "CFHTTPMessageCreateRequest");
  SetHeader set_header = (SetHeader)dlsym(net, "CFHTTPMessageSetHeaderFieldValue");
  StreamCreate stream_create = (StreamCreate)dlsym(net, "CFReadStreamCreateForHTTPRequest");
  void **http_version = (void **)dlsym(net, "kCFHTTPVersion1_1");
  void **redirect = (void **)dlsym(net, "kCFStreamPropertyHTTPShouldAutoredirect");
  void **true_value = (void **)dlsym(cf, "kCFBooleanTrue");
  int ok = 0;
  void *url_string = 0, *cf_url = 0, *method = 0, *request = 0, *stream = 0;
  void *header_name = 0, *header_value = 0;
  FILE *file = 0;
  char *buffer = 0;
  size_t used = 0, capacity = 0;
  if (!string_create || !url_create || !open || !read || !close || !release ||
      !message_create || !set_header || !stream_create || !http_version ||
      !*http_version) goto done;
  url_string = string_create(0, url, UPDATE_UTF8);
  cf_url = url_string ? url_create(0, url_string, 0) : 0;
  method = string_create(0, "GET", UPDATE_UTF8);
  request = cf_url && method
                ? message_create(0, method, cf_url, *http_version)
                : 0;
  header_name = string_create(0, "User-Agent", UPDATE_UTF8);
  header_value = string_create(0, "HoshimiLocalify-iOS/38", UPDATE_UTF8);
  if (!request || !header_name || !header_value) goto done;
  set_header(request, header_name, header_value);
  stream = stream_create(0, request);
  if (!stream) goto done;
  if (set_property && redirect && *redirect && true_value && *true_value)
    set_property(stream, *redirect, *true_value);
  if (!open(stream)) goto done;
  if (output_path) {
    file = fopen(output_path, "wb");
    if (!file) goto done;
  } else {
    capacity = 65536;
    buffer = malloc(capacity);
    if (!buffer) goto done;
  }
  unsigned char chunk[32768];
  for (;;) {
    intptr_t got = read(stream, chunk, sizeof(chunk));
    if (got < 0) goto done;
    if (!got) break;
    if (file) {
      if (fwrite(chunk, 1, (size_t)got, file) != (size_t)got) goto done;
    } else {
      if (used + (size_t)got + 1 > 2 * 1024 * 1024) goto done;
      if (used + (size_t)got + 1 > capacity) {
        size_t next = capacity * 2;
        while (next < used + (size_t)got + 1) next *= 2;
        char *grown = malloc(next);
        if (!grown) goto done;
        memcpy(grown, buffer, used); free(buffer); buffer = grown; capacity = next;
      }
      memcpy(buffer + used, chunk, (size_t)got); used += (size_t)got;
    }
  }
  if (buffer) buffer[used] = 0;
  ok = 1;
done:
  if (file) fclose(file);
  if (stream) { close(stream); release(stream); }
  if (header_value) release(header_value);
  if (header_name) release(header_name);
  if (request) release(request);
  if (method) release(method);
  if (cf_url) release(cf_url);
  if (url_string) release(url_string);
  dlclose(net); dlclose(cf);
  if (!ok) { free(buffer); if (output_path) remove(output_path); return 0; }
  if (memory) *memory = buffer; else free(buffer);
  if (memory_size) *memory_size = used;
  return 1;
}

static int update_json_string(const char *start, const char *end,
                              const char *key, char *output, size_t capacity) {
  char marker[128];
  int marker_length = snprintf(marker, sizeof(marker), "\"%s\"", key);
  if (marker_length <= 0 || (size_t)marker_length >= sizeof(marker)) return 0;
  const char *p = start;
  while (p < end) {
    const char *found = strstr(p, marker);
    if (!found || found >= end) return 0;
    p = found + marker_length;
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
    if (p >= end || *p++ != ':') continue;
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
    if (p >= end || *p++ != '"') continue;
    size_t used = 0;
    while (p < end && *p != '"') {
      char c = *p++;
      if (c == '\\' && p < end) {
        c = *p++;
        if (c == 'n') c = '\n'; else if (c == 'r') c = '\r';
        else if (c == 't') c = '\t'; else if (c == '/') c = '/';
      }
      if (used + 1 >= capacity) return 0;
      output[used++] = c;
    }
    if (p >= end) return 0;
    output[used] = 0;
    return 1;
  }
  return 0;
}

static int update_parse_release(const char *json, size_t length, char version[128],
                                char asset_url[2048]) {
  const char *end = json + length;
  if (!update_json_string(json, end, "tag_name", version, 128) ||
      !update_safe_version(version)) return 0;
  const char *assets = strstr(json, "\"assets\"");
  if (!assets) return 0;
  const char *p = assets;
  while (p < end && *p != '[') ++p;
  if (p >= end) return 0;
  ++p;
  while (p < end) {
    while (p < end && *p != '{' && *p != ']') ++p;
    if (p >= end || *p == ']') break;
    const char *object_start = p;
    int depth = 0, quoted = 0, escaped = 0;
    for (; p < end; ++p) {
      char c = *p;
      if (quoted) {
        if (escaped) escaped = 0;
        else if (c == '\\') escaped = 1;
        else if (c == '"') quoted = 0;
      } else if (c == '"') quoted = 1;
      else if (c == '{') ++depth;
      else if (c == '}' && --depth == 0) { ++p; break; }
    }
    if (depth != 0) return 0;
    const char *object_end = p;
    char name[512];
    if (!update_json_string(object_start, object_end, "name", name, sizeof(name)))
      continue;
    size_t name_length = strlen(name);
    if (name_length >= 4 && !strcmp(name + name_length - 4, ".zip") &&
        update_json_string(object_start, object_end, "browser_download_url",
                           asset_url, 2048))
      return 1;
  }
  return 0;
}

static void *update_worker(void *unused) {
  (void)unused;
  sleep(10);
  update_write_setting("translationDataUpdateStatus", "업데이트 확인 중");
  char *json = 0; size_t json_size = 0;
  if (!update_http_get(UPDATE_API_URL, 0, &json, &json_size)) {
    update_write_setting("translationDataUpdateStatus", "업데이트 확인 실패");
    record("UPDATE FAIL: GitHub release API request failed");
    return 0;
  }
  char version[128], asset_url[2048];
  int parsed = update_parse_release(json, json_size, version, asset_url);
  free(json);
  if (!parsed) {
    update_write_setting("translationDataUpdateStatus", "릴리스 정보 해석 실패");
    record("UPDATE FAIL: release JSON or zip asset invalid");
    return 0;
  }
  record("UPDATE RELEASE: current=%s latest=%s asset=%s",
         update_current_version[0] ? update_current_version : "unknown",
         version, asset_url);
  update_write_setting("latestTranslationDataVersion", version);
  if (!strcmp(version, update_current_version)) {
    update_write_setting("translationDataUpdateStatus", "최신 버전");
    record("UPDATE CURRENT: version=%s", version);
    return 0;
  }
  const char *home = getenv("HOME");
  char root[4096], zip_path[4096];
  int root_length = home ? snprintf(root, sizeof(root),
      "%s/Library/Application Support/HoshimiLocalAPI/versions/%s", home, version) : -1;
  if (root_length <= 0 || (size_t)root_length >= sizeof(root) ||
      !update_mkdirs(root) ||
      !update_copy_path(zip_path, sizeof(zip_path), root, "remote.zip.tmp")) {
    update_write_setting("translationDataUpdateStatus", "저장 경로 생성 실패");
    return 0;
  }
  update_write_setting("translationDataUpdateStatus", "새 데이터 다운로드 중");
  record("UPDATE DOWNLOAD: version=%s", version);
  if (!update_http_get(asset_url, zip_path, 0, 0)) {
    update_write_setting("translationDataUpdateStatus", "다운로드 실패");
    record("UPDATE FAIL: release zip download failed");
    return 0;
  }
  update_write_setting("translationDataUpdateStatus", "다운로드 검증 중");
  if (!update_extract_zip(zip_path, root) ||
      !update_validate_root(root, version, 0)) {
    remove(zip_path);
    update_write_setting("translationDataUpdateStatus", "호환되는 iOS 데이터 없음");
    record("UPDATE FAIL: zip validation/extraction failed or ios-data missing");
    return 0;
  }
  char complete[4096];
  if (!update_copy_path(complete, sizeof(complete), root, ".complete")) return 0;
  FILE *marker = fopen(complete, "wb");
  if (!marker || fwrite(version, 1, strlen(version), marker) != strlen(version)) {
    if (marker) fclose(marker);
    update_write_setting("translationDataUpdateStatus", "업데이트 저장 실패");
    return 0;
  }
  fclose(marker);
  remove(zip_path);
  update_write_setting("activeTranslationDataVersion", version);
  update_write_setting("translationDataUpdateStatus", "다운로드 완료 — 다음 실행부터 적용");
  record("UPDATE READY: version=%s applies on next launch", version);
  return 0;
}

static void update_start_if_enabled(void) {
  if (!api_assets_enabled || update_started) return;
  update_started = 1;
  pthread_t worker;
  if (pthread_create(&worker, 0, update_worker, 0) == 0) {
    pthread_detach(worker);
    record("UPDATE ARMED: GitHub latest release background check");
  } else {
    update_write_setting("translationDataUpdateStatus", "업데이트 작업 시작 실패");
  }
}
