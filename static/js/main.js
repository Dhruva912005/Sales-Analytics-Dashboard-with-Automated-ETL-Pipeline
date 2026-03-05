let charts = {};

document.addEventListener('DOMContentLoaded', () => {
    loadFilters();
    loadDashboard();
});

async function loadFilters() {
    const res = await fetch('/api/filter-options');
    const data = await res.json();
    fillSelect('categorySelect', data.categories);
    fillSelect('countrySelect', data.countries);
    fillSelect('brandSelect', data.brands);
}

function fillSelect(id, items) {
    const select = document.getElementById(id);
    if (!select) return;
    items.forEach(item => {
        const option = document.createElement('option');
        option.value = item;
        option.textContent = item;
        select.appendChild(option);
    });
}

async function applyFilters() {
    loadDashboard();
}

async function loadDashboard() {
    const date_range = document.getElementById('dateRange')?.value || 'last_30_days';
    const category = document.getElementById('categorySelect')?.value || 'all';
    const country = document.getElementById('countrySelect')?.value || 'all';
    const brand = document.getElementById('brandSelect')?.value || 'all';

    const url = `/api/advanced-chart-data?date_range=${date_range}&category=${category}&country=${country}&brand=${brand}`;
    
    const res = await fetch(url);
    const data = await res.json();

    updateKPIs(data.revenue_metrics);
    renderCategoryChart(data.category_analysis);
    renderGeoChart(data.geography_analysis);
    renderDailyTrend(data.trends.daily);
    renderMonthlyTrend(data.trends.monthly);
    renderWeeklyChart(data.weekly_pattern);
    renderPaymentChart(data.payment_methods);

    renderCustomerSegments(data.customer_segments);
}

function updateKPIs(kpi) {
    document.getElementById('totalRevenue').innerText = '₹' + kpi.total_revenue.toLocaleString();
    document.getElementById('totalOrders').innerText = kpi.total_orders;
    document.getElementById('totalCustomers').innerText = kpi.total_customers;
    document.getElementById('totalProfit').innerText = '₹' + kpi.total_profit.toLocaleString();
}

function renderCategoryChart(data) {
    const options = {
        series: data.map(d => d.revenue),
        labels: data.map(d => d.name),
        chart: { type: 'pie', height: 350 }
    };
    if (charts.categoryChart) charts.categoryChart.destroy();
    charts.categoryChart = new ApexCharts(document.querySelector("#categoryChart"), options);
    charts.categoryChart.render();
}

function renderGeoChart(data) {
    const options = {
        series: [{ data: data.map(d => d.revenue) }],
        xaxis: { categories: data.map(d => d.country) },
        chart: { type: 'bar', height: 350 }
    };
    if (charts.geoChart) charts.geoChart.destroy();
    charts.geoChart = new ApexCharts(document.querySelector("#geoChart"), options);
    charts.geoChart.render();
}

function renderDailyTrend(data) {
    const options = {
        series: [{ name: 'Revenue', data: data.map(d => d.revenue) }],
        xaxis: { categories: data.map(d => d.date) },
        chart: { type: 'line', height: 350 }
    };
    if (charts.dailyTrendChart) charts.dailyTrendChart.destroy();
    charts.dailyTrendChart = new ApexCharts(document.querySelector("#dailyTrendChart"), options);
    charts.dailyTrendChart.render();
}

function renderMonthlyTrend(data) {
    const options = {
        series: [{ name: 'Revenue', data: data.map(d => d.revenue) }],
        xaxis: { categories: data.map(d => d.month) },
        chart: { type: 'area', height: 350 }
    };
    if (charts.monthlyTrendChart) charts.monthlyTrendChart.destroy();
    charts.monthlyTrendChart = new ApexCharts(document.querySelector("#monthlyTrendChart"), options);
    charts.monthlyTrendChart.render();
}

function renderWeeklyChart(data) {
    const options = {
        series: [{ name: 'Revenue', data: data.map(d => d.revenue) }],
        xaxis: { categories: data.map(d => d.day) },
        chart: { type: 'bar', height: 350 }
    };
    if (charts.weeklyChart) charts.weeklyChart.destroy();
    charts.weeklyChart = new ApexCharts(document.querySelector("#weeklyChart"), options);
    charts.weeklyChart.render();
}

function renderPaymentChart(data) {
    const options = {
        series: data.map(d => d.revenue),
        labels: data.map(d => d.method),
        chart: { type: 'donut', height: 350 }
    };
    if (charts.paymentChart) charts.paymentChart.destroy();
    charts.paymentChart = new ApexCharts(document.querySelector("#paymentChart"), options);
    charts.paymentChart.render();
}

// ✅ FIXED Segments
function renderCustomerSegments(segments) {
    const ctx = document.getElementById('customerSegmentsChart');
    if (!ctx) return;

    if (charts.customerSegments) charts.customerSegments.destroy();

    charts.customerSegments = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: segments.map(s => s.segment),
            datasets: [{
                data: segments.map(s => s.count),
            }]
        }
    });
}
