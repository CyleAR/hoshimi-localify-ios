"""Exercise graphics hooks as ARM64 code with metadata-derived field offsets."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_SP,UC_ARM64_REG_LR,UC_ARM64_REG_X0
from test_generic_runtime import SUPPORT
ROOT=Path(__file__).resolve().parents[1]
class GraphicsRuntimeTests(unittest.TestCase):
 def test_android_graphics_policy(self):
  profile=json.loads((ROOT / "profiles/6.1.0.json").read_text(encoding="utf-8"))
  defines="#define HOSHIMI_QUALITY_SET_TARGET_RVA 1\n"+"".join(f"#define HOSHIMI_FIELD_{name.upper()} {value}\n" for name,value in profile["graphics_fields"].items())
  source=SUPPORT+defines+(ROOT / "hook/graphics.h").read_text(encoding="utf-8")+r'''
static char manager[256], controller[256], additional[256], rendering[512], names[64];
static int effective, seen_mode, seen_shadow;
static void set(void *p,int level,const void *m) { (void)p;(void)m;effective=level; }
static void *get_names(const void *m) { (void)m;return names; }
static uintptr_t thread(void) { return 7; }
static void *instance(const void *m) { (void)m;return controller; }
static int max_texture(const void *m) { (void)m;return 2048; }
static void camera_data(void *c,void *a,uint8_t f,void *d,const void *m) { (void)c;(void)f;(void)d;(void)m;seen_mode=*(int*)((char*)a+HOSHIMI_FIELD_AA_MODE); }
static uint8_t shadow(void *s,void *d,void **settings,int resolution,const void *m) { (void)s;(void)d;(void)settings;(void)m;seen_shadow=resolution;return 1; }
static struct GraphicsResolution resolution(int w,int h,struct GraphicsRatio r,int max,float scale,uint8_t first,const void *m) {
 (void)w;(void)h;(void)r;(void)max;(void)scale;(void)first;(void)m;return (struct GraphicsResolution){1920,1080};
}
__attribute__((section(".entry"))) int run(void) {
 graphics_enabled=1;graphics_quality=40;graphics_set=set;
 *(int*)(manager+HOSHIMI_FIELD_QUALITY_THREE_D)=20;
 graphics_set_hook(manager,20,0);
 if(effective!=40 || *(int*)(manager+HOSHIMI_FIELD_QUALITY_THREE_D)!=20)return 1;
 graphics_quality=100;graphics_names=get_names;*(uintptr_t*)(names+24)=6;
 *(int*)(manager+HOSHIMI_FIELD_QUALITY_UNITY)=999;graphics_before_apply(manager);
 if(*(int*)(manager+HOSHIMI_FIELD_QUALITY_UNITY)!=5)return 2;
 graphics_resolution=resolution;graphics_render_camera=controller;graphics_thread_id=thread;graphics_render_thread=7;
 graphics_scale=125;graphics_max=2160;
 struct GraphicsResolution value=graphics_resolution_hook(1920,1080,(struct GraphicsRatio){1,1},0,1,1,0);
 if(value.width!=2160 || value.height!=1216)return 3;
 graphics_instance=instance;graphics_controller_class=(void*)42;*(void**)controller=(void*)42;
 *(void**)(controller+HOSHIMI_FIELD_CAMERA_MAIN)=(void*)123;
 graphics_camera_data=camera_data;graphics_aa=2;
 *(int*)(additional+HOSHIMI_FIELD_AA_MODE)=1;additional[HOSHIMI_FIELD_AA_POST]=1;
 graphics_data_hook((void*)123,additional,1,0,0);
 if(seen_mode!=2 || *(int*)(additional+HOSHIMI_FIELD_AA_MODE)!=1)return 4;
 graphics_max_texture=max_texture;graphics_shadow_data=shadow;graphics_shadow=1024;
 *(void**)(rendering+HOSHIMI_FIELD_RENDER_CAMERA_DATA+HOSHIMI_FIELD_CAMERA_DATA_CAMERA)=(void*)123;
 graphics_shadow_hook(0,rendering,0,512,0);if(seen_shadow!=1024)return 5;
 graphics_shadow=4096;graphics_shadow_hook(0,rendering,0,512,0);if(seen_shadow!=512)return 6;
 graphics_enabled=0;graphics_set_hook(manager,20,0);if(effective!=20)return 7;
 return 0;
}
'''
  llvm=Path(os.environ["HOSHIMI_LLVM_BIN"])
  with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
   path=Path(folder);(path / "test.c").write_text(source,encoding="utf-8")
   (path / "link.ld").write_text("SECTIONS { . = 0x100000; .text : { *(.entry) *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }")
   subprocess.run([str(llvm / "clang.exe"),"--target=aarch64-none-elf","-ffreestanding","-O1","-c",str(path / "test.c"),"-o",str(path / "test.o")],check=True)
   subprocess.run([str(llvm / "ld.lld.exe"),"-T",str(path / "link.ld"),"--oformat=binary",str(path / "test.o"),"-o",str(path / "test.bin")],check=True)
   code=(path / "test.bin").read_bytes()
  uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);uc.mem_map(0x100000,0x1000000);uc.mem_write(0x100000,code)
  uc.reg_write(UC_ARM64_REG_SP,0x700000);uc.reg_write(UC_ARM64_REG_LR,0x200000)
  uc.emu_start(0x100000,0x200000,count=2000000)
  self.assertEqual(uc.reg_read(UC_ARM64_REG_X0),0)
