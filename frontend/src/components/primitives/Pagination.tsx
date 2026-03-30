import { Button } from './Button';
import styles from './Pagination.module.css';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  hasNext?: boolean;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, hasNext, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const showNext = hasNext ?? page < totalPages;

  if (total <= pageSize && page === 1) return null;

  return (
    <div className={styles.pagination}>
      <Button size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        ← Prev
      </Button>
      <span className={styles.pageInfo}>
        Page {page} of {totalPages} ({total} total)
      </span>
      <Button size="sm" disabled={!showNext} onClick={() => onPageChange(page + 1)}>
        Next →
      </Button>
    </div>
  );
}
