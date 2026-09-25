package hev.htproxy

/**
 * JNI binding shim for libhev-socks5-tunnel.so.
 *
 * The FQCN *must* stay hev.htproxy.TProxyService: the stock ndk-build
 * (no PKGNAME/CLSNAME overrides) registers its natives to exactly this
 * name — same contract the official AAR and Orbot/SocksTun use.
 * The .so itself is built in CI (see android-build.yml) and packaged
 * from jniLibs; no source changes needed here, ever.
 */
object TProxyService {
    external fun TProxyStartService(configPath: String, fd: Int): Boolean
    external fun TProxyStopService(): Boolean
    external fun TProxyIsRunning(): Boolean
    external fun TProxyGetStats(): LongArray

    init {
        System.loadLibrary("hev-socks5-tunnel")
    }
}
