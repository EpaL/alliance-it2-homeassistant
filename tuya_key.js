// Frida script: extract Tuya device localKey(s) from an OEM app (e.g. Alliance IT Pro)
// Strategy: find live Tuya DeviceBean objects on the heap and read their
// localKey / devId / name fields directly (robust to method-name obfuscation,
// because the Tuya SDK keeps the JSON field names localKey/devId/gwId).
Java.perform(function () {
  console.log("\n[*] Tuya local key extractor loaded — scanning heap...\n");

  function readField(obj, name) {
    try {
      var c = obj.getClass();
      while (c != null) {
        var fields = c.getDeclaredFields();
        for (var i = 0; i < fields.length; i++) {
          if (fields[i].getName() === name) {
            fields[i].setAccessible(true);
            var v = fields[i].get(obj);
            return v == null ? null : ("" + v);
          }
        }
        c = c.getSuperclass();
      }
    } catch (e) {}
    return undefined;
  }

  function classHasLocalKey(jclass) {
    try {
      var c = jclass;
      while (c != null) {
        var fs = c.getDeclaredFields();
        for (var i = 0; i < fs.length; i++) if (fs[i].getName() === "localKey") return true;
        c = c.getSuperclass();
      }
    } catch (e) {}
    return false;
  }

  var candidates = {};
  Java.enumerateLoadedClassesSync().forEach(function (name) {
    if (!/tuya|thing|DeviceBean|device.*bean/i.test(name)) return;
    try {
      var C = Java.use(name);
      if (classHasLocalKey(C.class)) candidates[name] = 1;
    } catch (e) {}
  });

  var names = Object.keys(candidates);
  console.log("[*] candidate bean classes with a localKey field: " + JSON.stringify(names));

  var seen = {};
  var count = 0;
  names.forEach(function (cn) {
    try {
      Java.choose(cn, {
        onMatch: function (inst) {
          var lk  = readField(inst, "localKey");
          var did = readField(inst, "devId") || readField(inst, "gwId") ||
                    readField(inst, "uuid")  || readField(inst, "id");
          var nm  = readField(inst, "name");
          if (lk && lk !== "null" && lk.length > 0) {
            var k = did + "|" + lk;
            if (!seen[k]) {
              seen[k] = 1; count++;
              console.log("\n================ TUYA DEVICE ================");
              console.log("  name     : " + nm);
              console.log("  devId    : " + did);
              console.log("  localKey : " + lk);
              console.log("============================================");
            }
          }
        },
        onComplete: function () {}
      });
    } catch (e) {}
  });

  console.log("\n[*] done. devices with keys found: " + count);
  if (count === 0) {
    console.log("[!] none found yet — make sure the app is logged in and you have");
    console.log("    opened the it2 device (dashboard) so its data is loaded, then re-run.");
  }
});
