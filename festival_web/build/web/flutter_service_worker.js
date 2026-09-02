'use strict';
const MANIFEST = 'flutter-app-manifest';
const TEMP = 'flutter-temp-cache';
const CACHE_NAME = 'flutter-app-cache';

const RESOURCES = {"flutter_bootstrap.js": "78fa2018760f0ea2027566e141821955",
"version.json": "b86ec84cf8120efae4c8a5572e12bb66",
"index.html": "8f93c69e759e17f8081ff6c5412d77e6",
"/": "8f93c69e759e17f8081ff6c5412d77e6",
"firebase-messaging-sw.js": "4ec5ff6938ac208b04893fee49a7990f",
"main.dart.js": "59da509aa6dbc46b3836c95fbf4008c2",
"flutter.js": "24bc71911b75b5f8135c949e27a2984e",
"favicon.png": "8f02bf1d994504f75c33b77d6e03a8ac",
"icons/apple-touch-icon.png": "c58235999e7b63a4860abb2970c34589",
"icons/Icon-192.png": "4093829d866d76e3d255576b0ce15f85",
"icons/Icon-maskable-192.png": "4093829d866d76e3d255576b0ce15f85",
"icons/Icon-maskable-512.png": "1f0a69138f6f043764f2cecf959d428f",
"icons/Icon-512.png": "1f0a69138f6f043764f2cecf959d428f",
"manifest.json": "a265d1707d1401720fde993019d9c89f",
"assets/NOTICES": "d766a12727e4cc09ca6f43f66ba4f885",
"assets/FontManifest.json": "a08ab7adae1b51bd3a99dc09b12c443b",
"assets/AssetManifest.bin.json": "34c7a015fb174c3c9ae6df21e1b63fb9",
"assets/packages/cupertino_icons/assets/CupertinoIcons.ttf": "1d2ae0567b5a2d55e87b4845483ffeba",
"assets/shaders/ink_sparkle.frag": "ecc85a2e95f5e9f53123dcaf8cb9b6ce",
"assets/shaders/stretch_effect.frag": "40d68efbbf360632f614c731219e95f0",
"assets/AssetManifest.bin": "0b3a916c24eb757df2c4c9863e663eef",
"assets/fonts/MaterialIcons-Regular.otf": "0c43ff74b87fcded4fa90f8c893ee374",
"assets/assets/images/mock_mbti_e_meongi_soft.png": "84bc09b6442d7421601d63a8a09601f0",
"assets/assets/images/mock_mbti_p_meongi_soft.png": "c14c76c4e08e6504f9a0cbf15d815997",
"assets/assets/images/mock_code_meongi_filled_compact.png": "a7416810d8e9a721fab0229724f7ceac",
"assets/assets/images/aiprofile_card.jpg": "818b39fa33ede21d2815fc422f2af405",
"assets/assets/images/aiprofile.png": "6cafb742ef1bb625dc6524a653c5ad82",
"assets/assets/images/loading_clay_dot.png": "87bd4f4451e8ff149a2f5f29626433f4",
"assets/assets/images/mainlogo.png": "cfa75a6d86655b5e457fb572ff242779",
"assets/assets/images/mock_mbti_f_meongi_soft.png": "6f1b70b687c7d606ebfb0163332db1e4",
"assets/assets/images/mock_mbti_n_meongi_soft.png": "46d2be1b39dc4dc72b7bd09896baabc3",
"assets/assets/images/ios_home_add_guide.png": "73c087955731b3d3b660d8645356e8d5",
"assets/assets/fonts/Griun_Gyuwon-Rg.ttf": "dc020d104381ca22a2dd7cffe5d5ebb9",
"assets/assets/fonts/NotoSansKR-Variable.ttf": "138709011225153288f260a9beacc90a",
"assets/assets/fonts/PretendardVariable.ttf": "872a6c5775ec910058a9a409a201972a",
"assets/assets/fonts/FestivalMeongiFilledWeb.ttf": "311b9988039059bbe5866797d14daf2a",
"assets/assets/fonts/BMKkubulimTTF.ttf": "b0943a508cdc6a7eca202ada8b38eacd",
"assets/assets/fonts/FestivalMeongiOutlineThick.ttf": "2be46a8389cfc09e281b411ede19fd29",
"canvaskit/skwasm.js": "8060d46e9a4901ca9991edd3a26be4f0",
"canvaskit/skwasm_heavy.js": "740d43a6b8240ef9e23eed8c48840da4",
"canvaskit/skwasm.js.symbols": "3a4aadf4e8141f284bd524976b1d6bdc",
"canvaskit/canvaskit.js.symbols": "a3c9f77715b642d0437d9c275caba91e",
"canvaskit/skwasm_heavy.js.symbols": "0755b4fb399918388d71b59ad390b055",
"canvaskit/skwasm.wasm": "7e5f3afdd3b0747a1fd4517cea239898",
"canvaskit/chromium/canvaskit.js.symbols": "e2d09f0e434bc118bf67dae526737d07",
"canvaskit/chromium/canvaskit.js": "a80c765aaa8af8645c9fb1aae53f9abf",
"canvaskit/chromium/canvaskit.wasm": "a726e3f75a84fcdf495a15817c63a35d",
"canvaskit/canvaskit.js": "8331fe38e66b3a898c4f37648aaf7ee2",
"canvaskit/canvaskit.wasm": "9b6a7830bf26959b200594729d73538e",
"canvaskit/skwasm_heavy.wasm": "b0be7910760d205ea4e011458df6ee01"};
// The application shell files that are downloaded before a service worker can
// start.
const CORE = ["main.dart.js",
"index.html",
"flutter_bootstrap.js",
"assets/AssetManifest.bin.json",
"assets/FontManifest.json"];

// During install, the TEMP cache is populated with the application shell files.
self.addEventListener("install", (event) => {
  self.skipWaiting();
  return event.waitUntil(
    caches.open(TEMP).then((cache) => {
      return cache.addAll(
        CORE.map((value) => new Request(value, {'cache': 'reload'})));
    })
  );
});
// During activate, the cache is populated with the temp files downloaded in
// install. If this service worker is upgrading from one with a saved
// MANIFEST, then use this to retain unchanged resource files.
self.addEventListener("activate", function(event) {
  return event.waitUntil(async function() {
    try {
      var contentCache = await caches.open(CACHE_NAME);
      var tempCache = await caches.open(TEMP);
      var manifestCache = await caches.open(MANIFEST);
      var manifest = await manifestCache.match('manifest');
      // When there is no prior manifest, clear the entire cache.
      if (!manifest) {
        await caches.delete(CACHE_NAME);
        contentCache = await caches.open(CACHE_NAME);
        for (var request of await tempCache.keys()) {
          var response = await tempCache.match(request);
          await contentCache.put(request, response);
        }
        await caches.delete(TEMP);
        // Save the manifest to make future upgrades efficient.
        await manifestCache.put('manifest', new Response(JSON.stringify(RESOURCES)));
        // Claim client to enable caching on first launch
        self.clients.claim();
        return;
      }
      var oldManifest = await manifest.json();
      var origin = self.location.origin;
      for (var request of await contentCache.keys()) {
        var key = request.url.substring(origin.length + 1);
        if (key == "") {
          key = "/";
        }
        // If a resource from the old manifest is not in the new cache, or if
        // the MD5 sum has changed, delete it. Otherwise the resource is left
        // in the cache and can be reused by the new service worker.
        if (!RESOURCES[key] || RESOURCES[key] != oldManifest[key]) {
          await contentCache.delete(request);
        }
      }
      // Populate the cache with the app shell TEMP files, potentially overwriting
      // cache files preserved above.
      for (var request of await tempCache.keys()) {
        var response = await tempCache.match(request);
        await contentCache.put(request, response);
      }
      await caches.delete(TEMP);
      // Save the manifest to make future upgrades efficient.
      await manifestCache.put('manifest', new Response(JSON.stringify(RESOURCES)));
      // Claim client to enable caching on first launch
      self.clients.claim();
      return;
    } catch (err) {
      // On an unhandled exception the state of the cache cannot be guaranteed.
      console.error('Failed to upgrade service worker: ' + err);
      await caches.delete(CACHE_NAME);
      await caches.delete(TEMP);
      await caches.delete(MANIFEST);
    }
  }());
});
// The fetch handler redirects requests for RESOURCE files to the service
// worker cache.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== 'GET') {
    return;
  }
  var origin = self.location.origin;
  var key = event.request.url.substring(origin.length + 1);
  // Redirect URLs to the index.html
  if (key.indexOf('?v=') != -1) {
    key = key.split('?v=')[0];
  }
  if (event.request.url == origin || event.request.url.startsWith(origin + '/#') || key == '') {
    key = '/';
  }
  // If the URL is not the RESOURCE list then return to signal that the
  // browser should take over.
  if (!RESOURCES[key]) {
    return;
  }
  // If the URL is the index.html, perform an online-first request.
  if (key == '/') {
    return onlineFirst(event);
  }
  event.respondWith(caches.open(CACHE_NAME)
    .then((cache) =>  {
      return cache.match(event.request).then((response) => {
        // Either respond with the cached resource, or perform a fetch and
        // lazily populate the cache only if the resource was successfully fetched.
        return response || fetch(event.request).then((response) => {
          if (response && Boolean(response.ok)) {
            cache.put(event.request, response.clone());
          }
          return response;
        });
      })
    })
  );
});
self.addEventListener('message', (event) => {
  // SkipWaiting can be used to immediately activate a waiting service worker.
  // This will also require a page refresh triggered by the main worker.
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
    return;
  }
  if (event.data === 'downloadOffline') {
    downloadOffline();
    return;
  }
});
// Download offline will check the RESOURCES for all files not in the cache
// and populate them.
async function downloadOffline() {
  var resources = [];
  var contentCache = await caches.open(CACHE_NAME);
  var currentContent = {};
  for (var request of await contentCache.keys()) {
    var key = request.url.substring(origin.length + 1);
    if (key == "") {
      key = "/";
    }
    currentContent[key] = true;
  }
  for (var resourceKey of Object.keys(RESOURCES)) {
    if (!currentContent[resourceKey]) {
      resources.push(resourceKey);
    }
  }
  return contentCache.addAll(resources);
}
// Attempt to download the resource online before falling back to
// the offline cache.
function onlineFirst(event) {
  return event.respondWith(
    fetch(event.request).then((response) => {
      return caches.open(CACHE_NAME).then((cache) => {
        cache.put(event.request, response.clone());
        return response;
      });
    }).catch((error) => {
      return caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((response) => {
          if (response != null) {
            return response;
          }
          throw error;
        });
      });
    })
  );
}
