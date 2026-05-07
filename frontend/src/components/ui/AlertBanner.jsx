export default function AlertBanner({ alert }) {
  if (!alert) return null;
  return (
    <div className="announcement-banner visible" role="alert">
      <div className="announcement-inner">
        <div>
          <strong>{alert.title}</strong>
          <p>{alert.message}</p>
        </div>
      </div>
    </div>
  );
}
