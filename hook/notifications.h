/* Local notification content created by this app, analogous to Android Builder hooks. */
static void *(*notification_message)(void *, void *, ...);
static void *(*notification_selector)(const char *);
static void (*notification_original[3])(void *, void *, void *);
static void *notification_string_class;
static void notification_set(unsigned index, void *self, void *selector, void *value) {
  if (!value) { notification_original[index](self, selector, value); return; }
  const char *text = (const char *)notification_message(value, notification_selector("UTF8String"));
  if (!text || strlen(text) > 16384) { notification_original[index](self, selector, value); return; }
  size_t length=0; int translated=0;
  char *localized=generic_translate_utf8(text,strlen(text),&length,&translated,1);
  void *replacement=localized ? ((void *(*)(void *,void *,const char *))notification_message)(notification_string_class,
      notification_selector("stringWithUTF8String:"),localized) : 0;
  notification_original[index](self,selector,replacement ? replacement : value);
  free(localized);
}
static void notification_title(void *self, void *cmd, void *value) { notification_set(0,self,cmd,value); }
static void notification_subtitle(void *self, void *cmd, void *value) { notification_set(1,self,cmd,value); }
static void notification_body(void *self, void *cmd, void *value) { notification_set(2,self,cmd,value); }
static void notifications_install(void) {
  void *objc=dlopen("/usr/lib/libobjc.A.dylib",RTLD_NOW);
  void *framework=dlopen("/System/Library/Frameworks/UserNotifications.framework/UserNotifications",RTLD_NOW);
  if (!objc || !framework) return;
  void *(*get_class)(const char *)=(void *(*)(const char *))dlsym(objc,"objc_getClass");
  void *(*get_method)(void *,void *)=(void *(*)(void *,void *))dlsym(objc,"class_getInstanceMethod");
  void *(*set_method)(void *,void *)=(void *(*)(void *,void *))dlsym(objc,"method_setImplementation");
  void *(*get_implementation)(void *)=(void *(*)(void *))dlsym(objc,"method_getImplementation");
  notification_selector=(void *(*)(const char *))dlsym(objc,"sel_registerName");
  notification_message=(void *(*)(void *,void *,...))dlsym(objc,"objc_msgSend");
  if (!get_class || !get_method || !set_method || !get_implementation || !notification_selector || !notification_message) return;
  notification_string_class=get_class("NSString");
  void *klass=get_class("UNMutableNotificationContent");
  if (!klass || !notification_string_class) return;
  const char *names[]={"setTitle:","setSubtitle:","setBody:"};
  void *callbacks[]={(void *)notification_title,(void *)notification_subtitle,(void *)notification_body};
  for (unsigned i=0;i<3;++i) {
    void *method=get_method(klass,notification_selector(names[i]));
    if (method) { notification_original[i]=(void (*)(void *,void *,void *))get_implementation(method); set_method(method,callbacks[i]); }
  }
  record("NOTIFICATIONS ARMED: local title/subtitle/body translation");
}
