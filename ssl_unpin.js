// Frida SSL unpinning for the Alliance "it Pro" React Native app.
// Neutralises the common pinning layers so an upstream proxy (mitmproxy) can
// read the app's Cognito/API/MQTT-over-wss traffic. Not Tuya-specific — the app
// has no Tuya SDK; we capture cloud traffic to see if the it2 localKey is served
// to the client.
Java.perform(function () {
  console.log("[*] SSL unpinning loaded");

  // 1) Android system TrustManagerImpl.verifyChain / checkTrustedRecursive
  try {
    var TMI = Java.use("com.android.org.conscrypt.TrustManagerImpl");
    TMI.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
      console.log("[+] bypass TrustManagerImpl.verifyChain for " + host);
      return untrustedChain;
    };
    console.log("[*] hooked TrustManagerImpl.verifyChain");
  } catch (e) { console.log("[-] TrustManagerImpl: " + e); }

  // 2) OkHttp3 CertificatePinner.check (RN networking rides OkHttp)
  try {
    var CP = Java.use("okhttp3.CertificatePinner");
    CP.check.overload("java.lang.String", "java.util.List").implementation = function (host, peerCertificates) {
      console.log("[+] bypass OkHttp CertificatePinner.check for " + host);
      return;
    };
    console.log("[*] hooked okhttp3.CertificatePinner.check");
  } catch (e) { console.log("[-] OkHttp CertificatePinner: " + e); }

  // 3) Generic X509TrustManager (SSLContext.init with a permissive TM)
  try {
    var X509TM = Java.use("javax.net.ssl.X509TrustManager");
    var SSLContext = Java.use("javax.net.ssl.SSLContext");
    var TrustManager = Java.registerClass({
      name: "com.frida.PermissiveTM",
      implements: [X509TM],
      methods: {
        checkClientTrusted: function () {},
        checkServerTrusted: function () {},
        getAcceptedIssuers: function () { return []; }
      }
    });
    var init = SSLContext.init.overload(
      "[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom");
    init.implementation = function (km, tm, sr) {
      console.log("[+] override SSLContext.init with permissive TrustManager");
      init.call(this, km, [TrustManager.$new()], sr);
    };
    console.log("[*] hooked SSLContext.init");
  } catch (e) { console.log("[-] SSLContext: " + e); }

  console.log("[*] unpinning hooks installed");
});
