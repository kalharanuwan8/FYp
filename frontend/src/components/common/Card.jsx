
export default function Card({ children, className = '', as: Tag = 'div', ...props }) {
  return (
    <Tag
      className={`bg-surface rounded-[var(--radius-card)] border border-border shadow-soft ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
}
