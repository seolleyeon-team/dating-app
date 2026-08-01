/* eslint-disable no-undef */
importScripts('https://www.gstatic.com/firebasejs/11.6.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/11.6.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyC8s000lBAIPJG1TyWtPFErGqV2FgSO0mQ',
  authDomain: 'seolleyeon-festival.firebaseapp.com',
  projectId: 'seolleyeon-festival',
  storageBucket: 'seolleyeon-festival.firebasestorage.app',
  messagingSenderId: '597362454449',
  appId: '1:597362454449:web:29c6a2d1a1643d5aef5790',
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = payload.notification?.title || '설레연';
  const body = payload.notification?.body || '새 메시지가 왔습니다';
  const options = {
    body,
    icon: '/icons/Icon-192.png',
    badge: '/icons/Icon-192.png',
    data: payload.data || {},
    tag: payload.data?.roomId || 'festival-chat',
  };
  return self.registration.showNotification(title, options);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const roomId = event.notification?.data?.roomId;
  const targetUrl = roomId ? `/chat?room=${encodeURIComponent(roomId)}` : '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.postMessage({ type: 'festival_chat_open', roomId });
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
      return undefined;
    }),
  );
});
