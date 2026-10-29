"""Android DictionaryPatterns input serialization (append-only HSGEN2 extension)."""
import json
import re
import struct

def groups(root):
 path=root / "local-files/prefill_dictionary.json"
 document=json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
 result={}
 if not isinstance(document,dict): return result
 for name,values in document.items():
  if not name or name.startswith("_") or name.isascii() and name.isdigit() or "{" in name or "}" in name or not isinstance(values,dict): continue
  entries={k:v for k,v in values.items() if k and isinstance(v,str) and v}
  for value in list(entries.values()): entries.setdefault(value,value)
  result[name]=entries
 return result

def has_placeholder(source, dictionary):
 return any(name in dictionary for name in re.findall(r"\{([^{}]*)\}",source))

def valid_pattern(source,target,dictionary):
 slots=set()
 def tokenize(text,replacement):
  count=0;last=0;previous_number=False
  for match in re.finditer(r"\{([^{}]*)\}",text):
   name=match[1];number=name.isascii() and name.isdigit();known=number or name in dictionary
   if not known:
    if replacement and match[0] not in source: return False
    continue
   if match.start()>last: count+=1;previous_number=False
   if number and previous_number and not replacement: return False
   if replacement and name not in slots: return False
   slots.add(name);count+=1;previous_number=number;last=match.end()
  return count+(last<len(text))<=64
 return bool(source and target and tokenize(source,False) and tokenize(target,True))


def compile_dictionary(patterns,dictionary):
 pool=bytearray(b"\0");offsets={"":0}
 def intern(text):
  if text not in offsets: offsets[text]=len(pool);pool.extend(text.encode()+b"\0")
  return offsets[text]
 def literal_length(text):
  return len(re.sub(r"\{([^{}]*)\}",lambda m:"" if m[1] in dictionary or m[1].isascii() and m[1].isdigit() else m[0],text).encode())
 rows=[]
 for source,target in sorted(patterns.items(),key=lambda p:(-literal_length(p[0]),p[0].encode())):
  if not valid_pattern(source,target,dictionary): continue
  rows.append(struct.pack("<2I",intern(source),intern(target)))
 entries=[]
 for group,values in sorted(dictionary.items()):
  for source,target in sorted(values.items(),key=lambda p:(-len(p[0].encode()),p[0].encode())):
   entries.append(struct.pack("<3I",intern(group),intern(source),intern(target)))
 offset=24+len(rows)*8+len(entries)*12
 return struct.pack("<8s4I",b"HSDICT1",len(rows),len(entries),offset,offset+len(pool))+b"".join(rows)+b"".join(entries)+pool
