import { useState, useEffect } from 'react';
import { 
  Search, 
  UserPlus, 
  CheckCircle, 
  XCircle, 
  Shield, 
  GraduationCap, 
  BookOpen, 
  ChevronLeft, 
  ChevronRight,
  AlertTriangle,
  X,
  UploadCloud
} from 'lucide-react';
import { adminService } from '../../services/adminService';
import CreateUserModal from '../../components/admin/CreateUserModal';
import CsvImportModal from '../../components/admin/CsvImportModal';

export const UserManagement = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filters & Pagination
  const [roleFilter, setRoleFilter] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);

  // Modals
  const [createUserModalOpen, setCreateUserModalOpen] = useState(false);
  const [csvImportModalOpen, setCsvImportModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [updating, setUpdating] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.getUsers({
        role: roleFilter,
        search,
        page,
        per_page: 10,
      });
      setUsers(data.users || []);
      setTotalPages(data.pages || 1);
      setTotalUsers(data.total || 0);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to fetch users');
    } finally {
      setLoading(false);
    }
  };

  // Explicit design: search is intentionally omitted from the useEffect dependency array
  // to avoid triggering API calls on every single keystroke. Search is submitted via handleSearchSubmit.
  useEffect(() => {
    fetchUsers();
  }, [roleFilter, page]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchUsers();
  };

  const openStatusConfirm = (user) => {
    setSelectedUser(user);
    setConfirmModalOpen(true);
  };

  const handleToggleStatus = async () => {
    if (!selectedUser) return;
    setUpdating(true);
    try {
      await adminService.updateUserStatus(selectedUser.id, !selectedUser.is_active);
      setConfirmModalOpen(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update user status');
    } finally {
      setUpdating(false);
    }
  };

  const getRoleBadge = (role) => {
    const roleClean = String(role).toLowerCase();
    if (roleClean === 'admin') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
          <Shield className="w-3.5 h-3.5" />
          <span>Admin</span>
        </span>
      );
    } else if (roleClean === 'teacher') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
          <BookOpen className="w-3.5 h-3.5" />
          <span>Teacher</span>
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-primary-soft text-sky-800 border border-primary/30">
          <GraduationCap className="w-3.5 h-3.5" />
          <span>Student</span>
        </span>
      );
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text tracking-tight">User Management</h1>
          <p className="text-xs text-text-muted font-medium mt-1">
            Manage user accounts, roles, and status across the platform ({totalUsers} total users).
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCsvImportModalOpen(true)}
            className="bg-bg hover:bg-border text-text text-xs font-semibold py-2.5 px-4 rounded-xl flex items-center gap-2 border border-border transition-all cursor-pointer"
          >
            <UploadCloud className="w-4 h-4 text-primary" />
            <span>Import Users</span>
          </button>

          <button
            onClick={() => setCreateUserModalOpen(true)}
            className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-medium py-2.5 px-4 rounded-xl flex items-center gap-2 shadow-sm transition-all cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            <span>Create User</span>
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-surface border border-border/80 rounded-2xl p-4 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Role Tabs */}
        <div className="flex items-center gap-1.5 bg-bg/80 p-1 rounded-xl w-full md:w-auto text-xs font-semibold">
          {[
            { label: 'All Roles', value: '' },
            { label: 'Students', value: 'student' },
            { label: 'Teachers', value: 'teacher' },
            { label: 'Admins', value: 'admin' },
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => {
                setRoleFilter(tab.value);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                roleFilter === tab.value
                  ? 'bg-surface text-primary shadow-sm font-bold'
                  : 'text-text-muted hover:text-text'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} className="w-full md:w-72 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name or email..."
              className="w-full pl-9 pr-3 py-2 bg-bg border border-border rounded-xl text-xs text-text focus:outline-none focus:border-primary focus:bg-surface"
            />
          </div>
          <button
            type="submit"
            className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-semibold px-3 py-2 rounded-xl transition-all cursor-pointer"
          >
            Search
          </button>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-4 rounded-xl">
          {error}
        </div>
      )}

      {/* Users Table */}
      <div className="bg-surface border border-border/80 rounded-2xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-text-muted text-xs font-medium">
            Loading user list...
          </div>
        ) : users.length === 0 ? (
          <div className="p-12 text-center text-text-muted text-xs font-medium">
            No users found matching current filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-bg border-b border-border text-text-muted font-bold uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="py-3.5 px-6">User</th>
                  <th className="py-3.5 px-6">Role</th>
                  <th className="py-3.5 px-6">Consent / Details</th>
                  <th className="py-3.5 px-6">Status</th>
                  <th className="py-3.5 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-xs text-text">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-bg/60 transition-colors">
                    <td className="py-4 px-6">
                      <div className="font-bold text-text">{u.first_name} {u.last_name}</div>
                      <div className="text-text-muted text-[11px] font-mono">{u.email}</div>
                    </td>
                    <td className="py-4 px-6">
                      {getRoleBadge(u.role)}
                    </td>
                    <td className="py-4 px-6">
                      {u.role === 'student' ? (
                        <div className="space-y-1">
                          {u.guardian_consent_given ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 text-[11px] font-semibold">
                              <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                              <span>Guardian Granted</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-amber-700 text-[11px] font-semibold">
                              <XCircle className="w-3.5 h-3.5 text-amber-500" />
                              <span>Consent Pending</span>
                            </span>
                          )}
                          {u.pseudonym_id && (
                            <div className="text-[10px] text-text-muted font-mono">
                              ID: {u.pseudonym_id.slice(0, 8)}...
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-text-muted italic text-[11px]">N/A</span>
                      )}
                    </td>
                    <td className="py-4 px-6">
                      {u.is_active ? (
                        <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Active
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-bg text-text-muted border border-border">
                          Deactivated
                        </span>
                      )}
                    </td>
                    <td className="py-4 px-6 text-right">
                      <button
                        onClick={() => openStatusConfirm(u)}
                        className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
                          u.is_active
                            ? 'text-red-700 bg-red-50 border-red-200 hover:bg-red-100'
                            : 'text-emerald-700 bg-emerald-50 border-emerald-200 hover:bg-emerald-100'
                        }`}
                      >
                        {u.is_active ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="bg-bg border-t border-border/80 px-6 py-3 flex items-center justify-between text-xs text-text-muted font-medium">
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="p-1.5 rounded-lg border border-border hover:bg-surface disabled:opacity-40 cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="p-1.5 rounded-lg border border-border hover:bg-surface disabled:opacity-40 cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create User Modal */}
      <CreateUserModal
        isOpen={createUserModalOpen}
        onClose={() => setCreateUserModalOpen(false)}
        onSuccess={fetchUsers}
      />

      {/* CSV Bulk Import Modal */}
      <CsvImportModal
        isOpen={csvImportModalOpen}
        onClose={() => setCsvImportModalOpen(false)}
        onSuccess={fetchUsers}
      />

      {/* Confirm Deactivation / Reactivation Modal */}
      {confirmModalOpen && selectedUser && (
        <div className="fixed inset-0 bg-surface/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-surface rounded-2xl p-6 max-w-sm w-full shadow-xl space-y-4">
            <div className="flex items-center gap-3 text-amber-600">
              <AlertTriangle className="w-6 h-6" />
              <h3 className="text-base font-bold text-text">
                {selectedUser.is_active ? 'Deactivate User?' : 'Reactivate User?'}
              </h3>
            </div>
            <p className="text-xs text-text-muted leading-relaxed">
              Are you sure you want to {selectedUser.is_active ? 'deactivate' : 'reactivate'} account for{' '}
              <strong>{selectedUser.first_name} {selectedUser.last_name}</strong> ({selectedUser.email})?
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setConfirmModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg cursor-pointer"
              >
                Cancel
              </button>
              <button
                disabled={updating}
                onClick={handleToggleStatus}
                className={`px-4 py-2 text-xs font-semibold text-white rounded-lg cursor-pointer transition-all ${
                  selectedUser.is_active
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {updating ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagement;
