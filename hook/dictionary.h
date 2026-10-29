/* Bounded dictionary-placeholder matching, following Android DictionaryPatterns. */
struct DictHeader { char magic[8]; uint32_t patterns, entries, pool, size; };
struct DictToken { const char *text; size_t length; int kind, slot; };
struct DictCapture { const char *source, *value; size_t length; };
struct DictContext {
  const struct DictHeader *header;
  struct DictToken tokens[64];
  unsigned count;
  struct DictCapture captures[64];
  const char *input; size_t length; unsigned *budget;
};
static const char *dict_string(const struct DictHeader *h, uint32_t offset) {
  if (offset >= h->size - h->pool) return 0;
  const char *text = (const char *)h + h->pool + offset;
  for (const char *p = text; p < (const char *)h + h->size; ++p) if (!*p) return text;
  return 0;
}
static int dict_equal(const char *text, size_t length, const char *value) {
  return value && strlen(value) == length && !memcmp(text, value, length);
}
static int dict_group(const struct DictHeader *h, const char *name, size_t length) {
  const uint32_t *rows = (const uint32_t *)((const char *)h + 24 + h->patterns * 8);
  for (uint32_t i = 0; i < h->entries; ++i)
    if (dict_equal(name, length, dict_string(h, rows[i*3]))) return 1;
  return 0;
}
static int dict_tokenize(struct DictContext *c, const char *text) {
  size_t length = strlen(text), start = 0;
  for (size_t i = 0; i < length; ++i) {
    if (text[i] != '{') continue;
    size_t end = i + 1;
    while (end < length && text[end] != '}') ++end;
    if (end == length) break;
    size_t n = end - i - 1;
    int number = n > 0;
    for (size_t j = i+1; j < end; ++j) if (text[j] < '0' || text[j] > '9') number = 0;
    int kind = number ? 1 : dict_group(c->header, text+i+1, n) ? 2 : 0;
    if (!kind) { i = end; continue; }
    if (c->count >= 62) return 0;
    if (i > start) c->tokens[c->count++] = (struct DictToken){text+start, i-start, 0, -1};
    if (number && c->count && c->tokens[c->count-1].kind == 1) return 0;
    int slot = (int)c->count;
    for (unsigned j = 0; j < c->count; ++j)
      if (c->tokens[j].kind && c->tokens[j].length == n && !memcmp(c->tokens[j].text, text+i+1, n)) { slot=c->tokens[j].slot; break; }
    c->tokens[c->count++] = (struct DictToken){text+i+1, n, kind, slot};
    start = end+1; i=end;
  }
  if (start < length) {
    if (c->count == 64) return 0;
    c->tokens[c->count++] = (struct DictToken){text+start,length-start,0,-1};
  }
  return 1;
}
static size_t dict_number(const char *text, size_t remaining, int *digit) {
  unsigned char ch = (unsigned char)*text;
  if (ch >= '0' && ch <= '9') { *digit=1; return 1; }
  if (ch=='+' || ch=='-' || ch=='.' || ch==',' || ch=='%') return 1;
  if (remaining>=3 && ch==0xef && (unsigned char)text[1]==0xbc && (unsigned char)text[2]>=0x90 && (unsigned char)text[2]<=0x99) { *digit=1; return 3; }
  const char *symbols[]={"＋","－","％","，","×"};
  for (unsigned i=0;i<5;++i) { size_t n=strlen(symbols[i]); if (remaining>=n && !memcmp(text,symbols[i],n)) return n; }
  return 0;
}
static int dict_match(struct DictContext *c, unsigned token, size_t pos) {
  if (!*c->budget) return 0;
  --*c->budget;
  if (token == c->count) return pos == c->length;
  struct DictToken *t=&c->tokens[token];
  if (!t->kind) return t->length<=c->length-pos && !memcmp(c->input+pos,t->text,t->length) && dict_match(c,token+1,pos+t->length);
  struct DictCapture *capture=&c->captures[t->slot];
  if (capture->source) return capture->length<=c->length-pos && !memcmp(c->input+pos,capture->source,capture->length) && dict_match(c,token+1,pos+capture->length);
  if (pos==c->length) return 0;
  if (t->kind==2) {
    const uint32_t *rows=(const uint32_t *)((const char *)c->header+24+c->header->patterns*8);
    for (uint32_t i=0;i<c->header->entries;++i) {
      const char *group=dict_string(c->header,rows[i*3]);
      if (!dict_equal(t->text,t->length,group)) continue;
      const char *src=dict_string(c->header,rows[i*3+1]), *dst=dict_string(c->header,rows[i*3+2]);
      if (!src || !dst || *src != c->input[pos]) continue;
      if (!*c->budget) return 0;
      --*c->budget;
      size_t n=strlen(src);
      if (n>c->length-pos || memcmp(c->input+pos,src,n)) continue;
      *capture=(struct DictCapture){c->input+pos,dst,n};
      if (dict_match(c,token+1,pos+n)) return 1;
      *capture=(struct DictCapture){0,0,0};
    }
  } else {
    size_t end=pos, first_digit_end=0; int digit=0;
    while (end<c->length) { size_t n=dict_number(c->input+end,c->length-end,&digit); if (!n) break; end+=n; if (digit && !first_digit_end) first_digit_end=end; }
    if (!digit) return 0;
    while (end>=first_digit_end) {
      if (!*c->budget) return 0;
      --*c->budget;
      if (end==c->length || ((unsigned char)c->input[end]&0xc0)!=0x80) {
        *capture=(struct DictCapture){c->input+pos,0,end-pos};
        if (dict_match(c,token+1,end)) return 1;
        *capture=(struct DictCapture){0,0,0};
      }
      --end;
    }
  }
  return 0;
}
static int dictionary_translate(const char *input, size_t length, char *output, size_t capacity, size_t *used) {
  if (length>16384 || generic_blob_size<36+12) return 0;
  const char *base=(const char *)generic_blob;
  if (memcmp(base+generic_blob_size-8,"HSDEND1",8)) return 0;
  uint32_t offset; memcpy(&offset,base+generic_blob_size-12,4);
  if (offset>generic_blob_size-12-24) return 0;
  const struct DictHeader *h=(const struct DictHeader *)(base+offset);
  if (memcmp(h->magic,"HSDICT1",8) || h->size!=generic_blob_size-12-offset || h->pool>h->size ||
      24ULL+h->patterns*8ULL+h->entries*12ULL!=h->pool) return 0;
  const uint32_t *patterns=(const uint32_t *)((const char *)h+24);
  unsigned budget=8192;
  for (uint32_t i=0;i<h->patterns && budget;++i) {
    const char *source=dict_string(h,patterns[i*2]), *target=dict_string(h,patterns[i*2+1]);
    if (!source || !target) continue;
    const char *anchor=source; size_t anchor_length=0, literal=0, source_length=strlen(source);
    for (size_t p=0;p<=source_length;++p) {
      if (p==source_length || source[p]=='{') {
        if (p-literal>anchor_length) { anchor=source+literal;anchor_length=p-literal; }
        if (p<source_length) { while (p<source_length && source[p]!='}') ++p; literal=p+1; }
      }
    }
    if (anchor_length) {
      int present=0;
      for (size_t p=0;p+anchor_length<=length;++p) if (!memcmp(input+p,anchor,anchor_length)) { present=1;break; }
      if (!present) continue;
    }
    struct DictContext c={0}; c.header=h; c.input=input; c.length=length; c.budget=&budget;
    if (!dict_tokenize(&c,source) || !dict_match(&c,0,0)) continue;
    size_t n=strlen(target); *used=0; output[0]=0;
    for (size_t p=0;p<n;) {
      int found=0;
      if (target[p]=='{') for (unsigned j=0;j<c.count;++j) {
        struct DictToken *t=&c.tokens[j];
        if (!t->kind || p+t->length+2>n || target[p+t->length+1]!='}' || memcmp(target+p+1,t->text,t->length)) continue;
        struct DictCapture *v=&c.captures[t->slot];
        if (!generic_append(output,capacity,used,v->value?v->value:v->source,v->value?strlen(v->value):v->length)) return 0;
        p+=t->length+2;found=1;break;
      }
      if (!found) { if (!generic_append(output,capacity,used,target+p,1)) return 0; ++p; }
    }
    return 1;
  }
  return 0;
}
