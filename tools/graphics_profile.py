"""Resolve Android graphics hook identities and field offsets from Dumper output."""
import json
import re
import struct

METHODS = {
 "quality_set": ("Solis.Common.SolisQualityManager$$SetQuality", "viii"),
 "quality_update": ("Solis.Common.SolisQualityManager$$Update", "vii"),
 "quality_init": ("Solis.Common.SolisQualityManager$$OnInitialize", "vii"),
 "camera_target": ("VL.Rendering.VLSRPCameraController$$UpdateRenderTarget", "viiiii"),
 "limited_resolution": ("VL.VLUtility$$GetLimitedResolution", "iiiiifii"),
 "camera_data": ("UnityEngine.Rendering.Universal.UniversalRenderPipeline$$InitializeCameraData", "viiiii"),
 "shadow_data": ("VL.Rendering.ActorShadowPass$$UpdateShadowData", "iiiiii"),
}
RUNTIME = {
 "camera_instance": ("VL.VLCameraController$$get_Instance", "ii"),
 "quality_names": ("UnityEngine.QualitySettings$$get_names", "ii"),
 "max_texture": ("UnityEngine.SystemInfo$$get_maxTextureSize", "ii"),
 "camera_destroy": ("VL.Rendering.VLSRPCameraController$$DestroyTargetTexture", "vii"),
}
FIELDS = {
 "quality_three_d": ("SolisQualityManager", "<ThreeD>k__BackingField"),
 "quality_unity": ("SolisQualityManager", "QualitySettingsLevel"),
 "camera_dynamic": ("VLSRPCameraController", "useDynamicScale"),
 "camera_main": ("VLSRPCameraController", "_mainCamera"),
 "aa_mode": ("UniversalAdditionalCameraData", "m_Antialiasing"),
 "aa_quality": ("UniversalAdditionalCameraData", "m_AntialiasingQuality"),
 "aa_post": ("UniversalAdditionalCameraData", "m_RenderPostProcessing"),
 "aa_type": ("UniversalAdditionalCameraData", "m_CameraType"),
 "render_camera_data": ("RenderingData", "cameraData"),
 "camera_data_camera": ("CameraData", "camera"),
}

def augment(profile, data, script, dump):
 from discover_hook_profile import codegen_modules, method_rows
 methods=json.loads(script.read_text(encoding="utf-8-sig"))["ScriptMethod"]
 reverse=method_rows(data,codegen_modules(data))
 def resolve(identity):
  matches={m["Address"]:m for m in methods if (m["Name"],m["TypeSignature"])==identity}
  if len(matches)!=1: raise ValueError(f"Graphics method ambiguous: {identity}")
  address,m=next(iter(matches.items()))
  site={"rva":address,"prologue":data[address:address+16].hex(),"method_identity":[m["Name"],m["Signature"],m["TypeSignature"]]}
  rows=reverse.get(address,[])
  if len(rows)==1: site.update(module=rows[0][0],row=rows[0][1])
  else:
   needle=struct.pack("<Q",address);slot=data.find(needle)
   if slot<0 or data.find(needle,slot+1)>=0: raise ValueError("Graphics pointer ambiguous")
   site["pointer_slot_rva"]=slot
  return site
 profile["extra_sites"]={name:resolve(identity) for name,identity in METHODS.items()}
 profile["runtime_methods"].update({name:resolve(identity) for name,identity in RUNTIME.items()})
 text=dump.read_text(encoding="utf-8-sig")
 fields={}
 for name,(klass,field) in FIELDS.items():
  match=re.search(r"public (?:class|struct) "+re.escape(klass)+r"(?: :| //)",text)
  if not match: raise ValueError(f"Graphics class missing: {klass}")
  block=text[match.start():text.index("// Methods",match.start())]
  found=re.search(r"\b"+re.escape(field)+r"; // 0x([0-9A-Fa-f]+)",block) if not field.startswith("<") else re.search(re.escape(field)+r"; // 0x([0-9A-Fa-f]+)",block)
  if not found: raise ValueError(f"Graphics field missing: {klass}.{field}")
  fields[name]=int(found[1],16)
 profile["graphics_fields"]=fields
 return profile
