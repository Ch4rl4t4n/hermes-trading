import client from "./client";

export async function listNotifications() {
  try {
    const { data } = await client.get("/api/notifications");
    return {
      items: Array.isArray(data?.notifications) ? data.notifications : [],
      unread: Number(data?.unread || 0),
      error: null,
    };
  } catch (error) {
    return { items: [], unread: 0, error };
  }
}

export async function getUnreadCount() {
  try {
    const { data } = await client.get("/api/notifications/unread-count");
    return { unread: Number(data?.unread || 0), error: null };
  } catch (error) {
    return { unread: 0, error };
  }
}

export async function markAllNotificationsRead() {
  try {
    const { data } = await client.post("/api/notifications/read");
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function markNotificationRead(id) {
  try {
    const { data } = await client.post(`/api/notifications/${encodeURIComponent(String(id))}/read`);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
