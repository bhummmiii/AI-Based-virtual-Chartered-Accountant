// ============================================================
// Common Type Definitions
// ============================================================

/** Standard API response wrapper */
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
  timestamp: string;
}

/** Paginated API response */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/** Standard pagination query params */
export interface PaginationParams {
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  search?: string;
}

/** Generic ID type */
export type ID = string | number;

/** Status enum for records */
export type Status = "active" | "inactive" | "pending" | "archived";

/** Date range filter */
export interface DateRange {
  startDate: string;
  endDate: string;
}

/** File upload metadata */
export interface FileUpload {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
  url: string;
  uploadedAt: string;
}

/** Navigation item */
export interface NavItem {
  title: string;
  href: string;
  icon?: string;
  badge?: string;
  children?: NavItem[];
  disabled?: boolean;
}
