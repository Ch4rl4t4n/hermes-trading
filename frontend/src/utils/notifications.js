export const requestPermission = async () => {
  if (!("Notification" in window)) return false;
  const result = await Notification.requestPermission();
  return result === "granted";
};

export const sendNotification = (title, body, options = {}) => {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  new Notification(title, {
    body,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    ...options,
  });
};
