// InvoiceAI JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm(this.dataset.confirm || 'Are you sure?')) {
                e.preventDefault();
            }
        });
    });

    // Format currency inputs
    const currencyInputs = document.querySelectorAll('.currency-input');
    currencyInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            const value = parseFloat(this.value);
            if (!isNaN(value)) {
                this.value = value.toFixed(2);
            }
        });
    });

    // Active nav link highlighting
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    navLinks.forEach(function(link) {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // Copy to clipboard functionality
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(function() {
            alert('Copied to clipboard!');
        }).catch(function(err) {
            console.error('Failed to copy:', err);
        });
    };

    // Form validation feedback
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Loading state for buttons (exclude status buttons which need their value preserved)
    const submitForms = document.querySelectorAll('form:not([action*="status"])');
    submitForms.forEach(function(form) {
        form.addEventListener('submit', function() {
            const button = form.querySelector('button[type="submit"]:not([name="status"])');
            if (button) {
                button.disabled = true;
                const originalText = button.innerHTML;
                button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Loading...';

                // Re-enable after 10 seconds (fallback)
                setTimeout(function() {
                    button.disabled = false;
                    button.innerHTML = originalText;
                }, 10000);
            }
        });
    });

    // Date input default to today
    const dateInputs = document.querySelectorAll('input[type="date"]:not([value])');
    dateInputs.forEach(function(input) {
        if (!input.value) {
            const today = new Date().toISOString().split('T')[0];
            input.value = today;
        }
    });

    // Tooltip initialization
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function(tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Utility functions
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

function formatDate(dateString) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

// Notifications functionality
(function() {
    const notificationBadge = document.getElementById('notificationBadge');
    const notificationList = document.getElementById('notificationList');
    const markAllReadBtn = document.getElementById('markAllRead');

    if (!notificationBadge) return; // Not logged in

    function loadNotifications() {
        fetch('/api/notifications')
            .then(response => response.json())
            .then(data => {
                // Update badge
                if (data.unread_count > 0) {
                    notificationBadge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                    notificationBadge.classList.remove('d-none');
                } else {
                    notificationBadge.classList.add('d-none');
                }

                // Update list
                if (data.notifications.length === 0) {
                    notificationList.innerHTML = '<div class="text-center py-3 text-muted"><small>No notifications</small></div>';
                    return;
                }

                let html = '';
                data.notifications.slice(0, 5).forEach(function(n) {
                    const timeAgo = getTimeAgo(new Date(n.created_at));
                    const unreadClass = n.is_read ? '' : 'bg-light';
                    html += `
                        <a class="dropdown-item py-2 ${unreadClass}" href="${n.link}" style="white-space: normal;">
                            <div class="d-flex align-items-start">
                                <i class="bi bi-eye text-primary me-2 mt-1"></i>
                                <div>
                                    <div class="fw-semibold small">${escapeHtml(n.title)}</div>
                                    <div class="text-muted small">${timeAgo}</div>
                                </div>
                            </div>
                        </a>
                    `;
                });
                notificationList.innerHTML = html;
            })
            .catch(err => {
                console.error('Failed to load notifications:', err);
                notificationList.innerHTML = '<div class="text-center py-3 text-muted"><small>Failed to load</small></div>';
            });
    }

    function getTimeAgo(date) {
        const seconds = Math.floor((new Date() - date) / 1000);
        if (seconds < 60) return 'Just now';
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        return date.toLocaleDateString();
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Mark all as read
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            fetch('/api/notifications/mark-all-read', { method: 'POST' })
                .then(() => {
                    notificationBadge.classList.add('d-none');
                    loadNotifications();
                });
        });
    }

    // Load on page load
    loadNotifications();

    // Refresh every 60 seconds
    setInterval(loadNotifications, 60000);
})();
