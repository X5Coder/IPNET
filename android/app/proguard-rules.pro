# hev JNI looks up hev.htproxy.TProxyService BY NAME at load time.
# Without this, R8 renames the class and JNI_OnLoad fails (the exact
# error the on-device diagnostics reported).
-keep class hev.htproxy.TProxyService { *; }
