// static/js/main.js

class SalesDashboard {
    constructor() {
        this.chartInstances = {};
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupTooltips();
        this.setupTheme();
    }
    
    setupEventListeners() {
        // Auto-refresh toggle
        const refreshToggle = document.getElementById('autoRefreshToggle');
        if (refreshToggle) {
            refreshToggle.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }
        
        // Export buttons
        document.querySelectorAll('.export-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const format = e.target.dataset.format;
                this.exportData(format);
            });
        });
        
        // Chart type toggle
        document.querySelectorAll('.chart-type-toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                const chartId = e.target.dataset.chart;
                const type = e.target.dataset.type;
                this.changeChartType(chartId, type);
            });
        });
        
        // Date range picker
        const dateRangePicker = document.getElementById('dateRangePicker');
        if (dateRangePicker) {
            dateRangePicker.addEventListener('change', () => {
                this.applyDateFilter();
            });
        }
        
        // Quick filters
        document.querySelectorAll('.quick-filter').forEach(filter => {
            filter.addEventListener('click', (e) => {
                const filterType = e.target.dataset.filter;
                const value = e.target.dataset.value;
                this.applyQuickFilter(filterType, value);
            });
        });
    }
    
    setupTooltips() {
        // Initialize Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
    
    setupTheme() {
        // Check for saved theme preference
        const savedTheme = localStorage.getItem('dashboard-theme') || 'dark';
        this.setTheme(savedTheme);
        
        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => {
                const currentTheme = document.documentElement.getAttribute('data-bs-theme');
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                this.setTheme(newTheme);
                localStorage.setItem('dashboard-theme', newTheme);
            });
        }
    }
    
    setTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        
        // Update chart colors based on theme
        if (window.updateChartColors) {
            window.updateChartColors(theme);
        }
    }
    
    startAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.refreshData();
        }, 300000); // 5 minutes
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
    
    async refreshData() {
        try {
            this.showLoading();
            
            const response = await fetch('/api/chart-data');
            const data = await response.json();
            
            // Update KPIs
            this.updateKPIs(data.kpis);
            
            // Update charts
            this.updateCharts(data);
            
            this.showToast('Data refreshed successfully', 'success');
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showToast('Error refreshing data', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    updateKPIs(kpis) {
        const kpiElements = {
            'total_orders': document.getElementById('kpiOrders'),
            'total_revenue': document.getElementById('kpiRevenue'),
            'total_customers': document.getElementById('kpiCustomers'),
            'avg_order_value': document.getElementById('kpiAvgOrder'),
            'total_quantity': document.getElementById('kpiQuantity'),
            'total_returns': document.getElementById('kpiReturns')
        };
        
        Object.entries(kpiElements).forEach(([key, element]) => {
            if (element && kpis[key]) {
                if (key.includes('revenue') || key.includes('value')) {
                    element.textContent = this.formatCurrency(kpis[key]);
                } else {
                    element.textContent = this.formatNumber(kpis[key]);
                }
            }
        });
    }
    
    updateCharts(data) {
        // Update each chart if it exists
        Object.keys(this.chartInstances).forEach(chartId => {
            const chartData = data[chartId];
            if (chartData && this.chartInstances[chartId]) {
                this.updateChart(chartId, chartData);
            }
        });
    }
    
    updateChart(chartId, data) {
        // This would be implemented based on your chart library
        console.log(`Updating chart ${chartId} with data:`, data);
    }
    
    async exportData(format) {
        try {
            this.showLoading('Exporting...');
            
            let url, filename;
            
            switch (format) {
                case 'csv':
                    url = '/export/csv';
                    filename = 'sales_export.csv';
                    break;
                case 'pdf':
                    url = '/export/pdf';
                    filename = 'sales_report.pdf';
                    break;
                case 'excel':
                    url = '/export/excel';
                    filename = 'sales_data.xlsx';
                    break;
                default:
                    throw new Error('Unsupported format');
            }
            
            const response = await fetch(url);
            const blob = await response.blob();
            
            // Create download link
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);
            
            this.showToast(`Exported successfully as ${format.toUpperCase()}`, 'success');
        } catch (error) {
            console.error('Export error:', error);
            this.showToast('Export failed', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    applyDateFilter() {
        const dateRangePicker = document.getElementById('dateRangePicker');
        if (!dateRangePicker) return;
        
        const dates = dateRangePicker.value.split(' to ');
        if (dates.length === 2) {
            const [startDate, endDate] = dates;
            this.filterByDateRange(startDate, endDate);
        }
    }
    
    async filterByDateRange(startDate, endDate) {
        try {
            this.showLoading('Applying filter...');
            
            const response = await fetch(`/api/filter?start_date=${startDate}&end_date=${endDate}`);
            const data = await response.json();
            
            this.updateKPIs(data.kpis);
            this.updateCharts(data);
            
            this.showToast(`Filter applied: ${startDate} to ${endDate}`, 'info');
        } catch (error) {
            console.error('Filter error:', error);
            this.showToast('Filter failed', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    applyQuickFilter(filterType, value) {
        console.log(`Applying filter: ${filterType} = ${value}`);
        // Implement filter logic based on your needs
    }
    
    changeChartType(chartId, type) {
        console.log(`Changing chart ${chartId} to type ${type}`);
        // Implement chart type switching logic
    }
    
    showLoading(message = 'Loading...') {
        // Create or show loading overlay
        let loadingOverlay = document.getElementById('loadingOverlay');
        
        if (!loadingOverlay) {
            loadingOverlay = document.createElement('div');
            loadingOverlay.id = 'loadingOverlay';
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="text-center">
                    <div class="spinner mb-3"></div>
                    <div class="text-light">${message}</div>
                </div>
            `;
            document.body.appendChild(loadingOverlay);
        } else {
            loadingOverlay.style.display = 'flex';
        }
    }
    
    hideLoading() {
        const loadingOverlay = document.getElementById('loadingOverlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    }
    
    showToast(message, type = 'info') {
        const toastContainer = document.querySelector('.toast-container') || this.createToastContainer();
        
        const toastId = 'toast-' + Date.now();
        const icon = {
            'success': 'check-circle',
            'error': 'exclamation-circle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        }[type];
        
        const toastHTML = `
            <div id="${toastId}" class="custom-toast mb-3" role="alert">
                <div class="d-flex">
                    <div class="toast-body p-3">
                        <i class="fas fa-${icon} text-${type} me-2"></i>
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-3 m-auto" 
                            data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHTML);
        const toastElement = document.getElementById(toastId);
        const bsToast = new bootstrap.Toast(toastElement, { delay: 3000 });
        bsToast.show();
        
        toastElement.addEventListener('hidden.bs.toast', function () {
            this.remove();
        });
    }
    
    createToastContainer() {
        const container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }
    
    formatCurrency(value) {
        return '₹' + parseInt(value).toLocaleString('en-IN');
    }
    
    formatNumber(value) {
        return parseInt(value).toLocaleString('en-IN');
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.dashboard = new SalesDashboard();
    
    // Initialize any third-party libraries
    if (typeof ApexCharts !== 'undefined') {
        window.initApexCharts();
    }
    
    // Setup any additional plugins
    setupPlugins();
});

function setupPlugins() {
    // Add any plugin initialization here
    console.log('Plugins initialized');
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SalesDashboard, debounce, throttle };
} 