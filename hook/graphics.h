/* Android graphics policy; offsets are generated from the exact IPA metadata. */
#ifdef HOSHIMI_QUALITY_SET_TARGET_RVA
static int graphics_enabled, graphics_quality, graphics_aa = -1, graphics_shadow;
static int graphics_scale = 77, graphics_max = 3384;
static void (*graphics_set)(void *, int, const void *);
static void (*graphics_update)(void *, const void *);
static void (*graphics_init)(void *, const void *);
static void (*graphics_camera_target)(void *, int, int, uint8_t, const void *);
struct GraphicsResolution { int32_t width, height; };
struct GraphicsRatio { float x, y; };
static struct GraphicsResolution (*graphics_resolution)(int, int, struct GraphicsRatio, int, float, uint8_t, const void *);
static void (*graphics_camera_data)(void *, void *, uint8_t, void *, const void *);
static uint8_t (*graphics_shadow_data)(void *, void *, void **, int, const void *);
static void *(*graphics_instance)(const void *);
static void (*graphics_destroy)(void *, const void *);
static void *(*graphics_names)(const void *);
static int (*graphics_max_texture)(const void *);
static void *graphics_manager, *graphics_render_camera, *graphics_built_camera;
static void *graphics_controller_class;
static uintptr_t (*graphics_thread_id)(void);
static uintptr_t graphics_render_thread;
static int graphics_game_quality, graphics_applied = -1, graphics_quality_count = -1;
static int graphics_quality_valid(int value) {
  return value == 10 || value == 20 || value == 30 || value == 40 || value == 100;
}
static int graphics_requested(void) {
  if (!graphics_enabled || !graphics_quality_valid(graphics_quality)) return 0;
  if (graphics_quality == 100 && graphics_quality_count < 0) {
    void *names = graphics_names ? graphics_names(0) : 0;
    uintptr_t count = names ? *(uintptr_t *)((char *)names + 24) : 0;
    graphics_quality_count = count <= 1024 ? (int)count : 0;
  }
  return graphics_quality == 100 && graphics_quality_count == 0 ? 0 : graphics_quality;
}
static void graphics_track(void *self) {
  if (graphics_manager != self) {
    graphics_manager = self;
    graphics_game_quality = *(int *)((char *)self + HOSHIMI_FIELD_QUALITY_THREE_D);
    graphics_applied = -1;
  }
}
static void graphics_set_hook(void *self, int level, const void *method) {
  graphics_track(self);
  graphics_game_quality = level;
  int requested = graphics_requested();
  int change = graphics_quality_valid(level) && (requested || graphics_applied > 0);
  int *field = (int *)((char *)self + HOSHIMI_FIELD_QUALITY_THREE_D);
  if (change) *field = 0;
  graphics_set(self, requested && graphics_quality_valid(level) ? requested : level, method);
  if (change) *field = level;
  graphics_applied = requested;
}
static void graphics_before_apply(void *self) {
  if (graphics_requested() != 100) return;
  uintptr_t count = (uintptr_t)graphics_quality_count;
  if (!count || count > 1024) return;
  int *level = (int *)((char *)self + HOSHIMI_FIELD_QUALITY_UNITY);
  if (*level < 0) *level = 0;
  if ((uintptr_t)*level >= count) *level = (int)count - 1;
}
static void graphics_update_hook(void *self, const void *method) {
  graphics_track(self);
  if (graphics_applied != graphics_requested() && graphics_quality_valid(graphics_game_quality))
    graphics_set_hook(self, graphics_game_quality, 0);
  graphics_update(self, method);
}
static void graphics_init_hook(void *self, const void *method) {
  graphics_manager = 0;
  graphics_applied = -1;
  graphics_init(self, method);
}
static void *graphics_main(void) {
  void *controller = graphics_instance(0);
  return controller && graphics_controller_class && *(void **)controller == graphics_controller_class ? *(void **)((char *)controller + HOSHIMI_FIELD_CAMERA_MAIN) : 0;
}
static void graphics_target_hook(void *self, int width, int height, uint8_t alpha, const void *method) {
  if (!graphics_enabled || !self || (width > 0 && height > 0)) {
    graphics_camera_target(self, width, height, alpha, method);
    return;
  }
  graphics_controller_class = *(void **)self;
  uintptr_t previous_thread = graphics_render_thread;
  graphics_render_thread = graphics_thread_id ? graphics_thread_id() : 0;
  uint8_t *dynamic = (uint8_t *)self + HOSHIMI_FIELD_CAMERA_DYNAMIC;
  uint8_t saved = *dynamic;
  void *previous = graphics_render_camera;
  /* Settings are read once per launch. Rebuild only once per controller. */
  if (graphics_built_camera != self) { graphics_destroy(self, 0); graphics_built_camera = self; }
  graphics_render_camera = self;
  *dynamic = 0;
  graphics_camera_target(self, width, height, alpha, method);
  *dynamic = saved;
  graphics_render_camera = previous;
  graphics_render_thread = previous_thread;
}
static struct GraphicsResolution graphics_resolution_hook(int w, int h, struct GraphicsRatio ratio,
    int max, float scale, uint8_t first, const void *method) {
  if (!graphics_enabled || !graphics_render_camera || !graphics_thread_id || graphics_render_thread != graphics_thread_id() || !first)
    return graphics_resolution(w, h, ratio, max, scale, first, method);
  struct GraphicsResolution result = graphics_resolution(w, h, ratio, 0, 1.0f, first, method);
  if (result.width <= 0 || result.height <= 0) return result;
  float effective = (float)graphics_scale / 100.0f;
  int longest = result.width > result.height ? result.width : result.height;
  if (effective > (float)graphics_max / longest) effective = (float)graphics_max / longest;
  int width = (int)((float)result.width * effective / 2.0f + 0.5f) * 2;
  int height = (int)((float)result.height * effective / 2.0f + 0.5f) * 2;
  result.width = width < 16 ? 16 : width > graphics_max ? graphics_max : width;
  result.height = height < 16 ? 16 : height > graphics_max ? graphics_max : height;
  return result;
}
static void graphics_data_hook(void *camera, void *additional, uint8_t final, void *data, const void *method) {
  if (!graphics_enabled || graphics_aa < 0 || !additional || camera != graphics_main() ||
      *(int *)((char *)additional + HOSHIMI_FIELD_AA_TYPE) != 0) {
    graphics_camera_data(camera, additional, final, data, method);
    return;
  }
  int *mode = (int *)((char *)additional + HOSHIMI_FIELD_AA_MODE);
  int *quality = (int *)((char *)additional + HOSHIMI_FIELD_AA_QUALITY);
  int saved_mode = *mode, saved_quality = *quality;
  if (*(uint8_t *)((char *)additional + HOSHIMI_FIELD_AA_POST) || graphics_aa == 0) {
    *mode = graphics_aa;
    if (graphics_aa == 2) *quality = 2;
  }
  graphics_camera_data(camera, additional, final, data, method);
  *mode = saved_mode;
  *quality = saved_quality;
}
static uint8_t graphics_shadow_hook(void *self, void *data, void **settings, int resolution, const void *method) {
  if (graphics_enabled && graphics_shadow && data && graphics_shadow <= graphics_max_texture(0)) {
    void *camera = *(void **)((char *)data + HOSHIMI_FIELD_RENDER_CAMERA_DATA + HOSHIMI_FIELD_CAMERA_DATA_CAMERA);
    if (camera && camera == graphics_main()) resolution = graphics_shadow;
  }
  return graphics_shadow_data(self, data, settings, resolution, method);
}
#else
static void graphics_before_apply(void *self) { (void)self; }
#endif
