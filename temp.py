import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from dataclasses import dataclass
from typing import Dict, Tuple, List

# Configuration and styling
st.set_page_config(
    page_title="Ride-Sharing Investment Analyzer",
    page_icon="🛵",
    layout="wide"
)

# Currency formatting function
def format_currency(value):
    """Format currency in lakhs for better readability"""
    if abs(value) >= 1_00_000:
        return f"₹{value/1_00_000:.2f}L"
    else:
        return f"₹{value:,.0f}"

def get_profit_color(value, cumulative_value=None):
    """Return color based on profit/loss, considering cumulative if provided"""
    if cumulative_value is not None:
        return "#28a745" if value >= 0 and cumulative_value >= 0 else "#dc3545"
    return "#28a745" if value >= 0 else "#dc3545"

@dataclass
class BusinessMetrics:
    """Data class to store calculated business metrics"""
    total_turnover: float
    net_revenue: float
    total_costs: float
    gross_profit: float
    profit_per_driver: float
    break_even_rides: float
    initial_investment: float = 0
    ev_payback_months: float = 0
    cost_breakdown: Dict[str, float] = None
    monthly_projections: Dict[str, List[float]] = None
    break_even_month: int = None
    roi_percentage: float = None
    total_3yr_profit: float = None

class RideShareEconomics:
    """Main class for calculating ride-sharing economics"""
    
    def __init__(self):
        self.revenue_share = {
            'aggregator': 0.03,  # 3% to aggregator
            'fleet': 0.93,       # 93% to fleet owner
            'app': 0.07          # 7% to app
        }
    
    def calculate_base_revenue(self, avg_ticket_size: float, rides_per_day: float, 
                             working_days: int, utilization_rate: float, num_drivers: int) -> float:
        """Calculate base revenue before commission splits"""
        monthly_rides = rides_per_day * working_days * utilization_rate / 100
        return avg_ticket_size * monthly_rides * num_drivers
    
    def calculate_monthly_projections(self, monthly_profit: float, monthly_costs: float, 
                                    monthly_revenue: float, monthly_turnover: float,
                                    num_drivers: int, initial_investment: float = 0, 
                                    months: int = 36) -> Dict[str, List[float]]:
        """Calculate month-by-month projections with cumulative profit"""
        projections = {
            'month': list(range(1, months + 1)),
            'total_turnover': [monthly_turnover] * months,
            'net_revenue': [monthly_revenue] * months,
            'total_costs': [monthly_costs] * months,
            'gross_profit': [monthly_profit] * months,
            'profit_per_driver': [monthly_profit / max(num_drivers, 1)] * months,
            'cumulative_profit': []
        }
        
        cumulative = -initial_investment
        for i in range(months):
            cumulative += monthly_profit
            projections['cumulative_profit'].append(cumulative)
            
        return projections
    
    def calculate_aggregator_model(self, params: Dict) -> BusinessMetrics:
        """Calculate metrics for aggregator-only model"""
        base_revenue = self.calculate_base_revenue(
            params['avg_ticket_size'], params['rides_per_day'], 
            params['working_days'], params['utilization_rate'], 
            params['num_agg_drivers']
        )
        
        net_revenue = base_revenue * self.revenue_share['aggregator']
        
        # Calculate costs
        # Driver acquisition cost - one-time cost amortized over expected tenure
        if params['driver_churn_rate'] > 0:
            expected_tenure_months = 100 / params['driver_churn_rate']
            monthly_acquisition_cost = (params['agg_driver_acquisition_cost'] * 
                                      params['num_agg_drivers'] / expected_tenure_months)
        else:
            monthly_acquisition_cost = 0
        
        # Monthly salary for aggregator drivers
        driver_salaries = 0
        
        ops_salary = params['agg_ops_salary']
        fixed_costs = params['fixed_costs']
        
        # Calculate taxes
        profit_before_tax = net_revenue - (monthly_acquisition_cost + driver_salaries + 
                                         ops_salary + fixed_costs)
        tax_amount = max(0, profit_before_tax * params['tax_rate'] / 100)
        
        total_costs = (monthly_acquisition_cost + driver_salaries + ops_salary + 
                      fixed_costs + tax_amount)
        
        cost_breakdown = {
            'Driver Salaries': driver_salaries,
            'Driver Acquisition (Monthly)': monthly_acquisition_cost,
            'Ops Team Salary': ops_salary,
            'Fixed Costs': fixed_costs,
            'Taxes': tax_amount
        }
        
        gross_profit = net_revenue - total_costs
        profit_per_driver = gross_profit / max(params['num_agg_drivers'], 1)
        
        # Break-even calculation
        if gross_profit <= 0:
            break_even_rides = float('inf')
            break_even_month = None
        else:
            contribution_per_ride = params['avg_ticket_size'] * self.revenue_share['aggregator']
            break_even_rides = total_costs / contribution_per_ride
            break_even_month = 1  # No initial investment for aggregator model
        
        # Monthly projections
        monthly_projections = self.calculate_monthly_projections(
            gross_profit, total_costs, net_revenue, base_revenue, params['num_agg_drivers']
        )
        
        # ROI calculation
        total_3yr_profit = gross_profit * 36
        roi_percentage = (total_3yr_profit / 1) * 100  # No initial investment
        
        return BusinessMetrics(
            total_turnover=base_revenue,
            net_revenue=net_revenue,
            total_costs=total_costs,
            gross_profit=gross_profit,
            profit_per_driver=profit_per_driver,
            break_even_rides=break_even_rides,
            break_even_month=break_even_month,
            initial_investment=0,
            roi_percentage=roi_percentage,
            total_3yr_profit=total_3yr_profit,
            cost_breakdown=cost_breakdown,
            monthly_projections=monthly_projections
        )
    
    def calculate_fleet_model(self, params: Dict) -> BusinessMetrics:
        """Calculate metrics for fleet-owner model"""
        base_revenue = self.calculate_base_revenue(
            params['avg_ticket_size'], params['rides_per_day'], 
            params['working_days'], params['utilization_rate'], 
            params['num_fleet_drivers']
        )
        
        net_revenue = base_revenue * self.revenue_share['fleet']
        
        # Calculate costs
        # Driver acquisition cost - one-time cost amortized over expected tenure
        if params['driver_churn_rate'] > 0:
            expected_tenure_months = 100 / params['driver_churn_rate']
            monthly_acquisition_cost = (params['fleet_driver_acquisition_cost'] * 
                                      params['num_fleet_drivers'] / expected_tenure_months)
        else:
            monthly_acquisition_cost = 0
        
        # Monthly salary for fleet drivers
        driver_salaries = params['driver_salary'] * params['num_fleet_drivers']
        
        # EV costs - one-time initial investment
        initial_ev_investment = params['ev_cost'] * params['num_fleet_drivers']
        
        # Maintenance and fuel costs still apply monthly
        maintenance_costs = params['ev_maintenance'] * params['num_fleet_drivers']
        fuel_costs = params['ev_fuel_cost'] * params['num_fleet_drivers'] * (params['utilization_rate'] / 100)
        fixed_costs = params['fixed_costs']
        
        # Calculate taxes
        profit_before_tax = net_revenue - (monthly_acquisition_cost + driver_salaries + 
                                         maintenance_costs + fuel_costs + fixed_costs)
        tax_amount = max(0, profit_before_tax * params['tax_rate'] / 100)
        
        total_monthly_costs = (monthly_acquisition_cost + driver_salaries + 
                             maintenance_costs + fuel_costs + fixed_costs + tax_amount)
        
        cost_breakdown = {
            'Driver Salaries': driver_salaries,
            'Driver Acquisition (Monthly)': monthly_acquisition_cost,
            'EV Investment (One-time)': initial_ev_investment,
            'Maintenance': maintenance_costs,
            'Fuel/Mileage': fuel_costs,
            'Fixed Costs': fixed_costs,
            'Taxes': tax_amount
        }
        
        gross_profit = net_revenue - total_monthly_costs
        profit_per_driver = gross_profit / max(params['num_fleet_drivers'], 1)
        
        # Break-even calculation (now considering initial investment)
        contribution_per_ride = params['avg_ticket_size'] * self.revenue_share['fleet']
        monthly_contribution = gross_profit
        
        if monthly_contribution <= 0:
            break_even_month = None
        else:
            break_even_month = int(np.ceil(initial_ev_investment / monthly_contribution)) + 1  # +1 because investment is at start
        
        # Break-even rides calculation (monthly)
        if gross_profit <= 0:
            break_even_rides = float('inf')
        else:
            break_even_rides = total_monthly_costs / contribution_per_ride
        
        # Monthly projections (accounting for initial investment)
        monthly_projections = self.calculate_monthly_projections(
            gross_profit, total_monthly_costs, net_revenue, base_revenue, 
            params['num_fleet_drivers'], initial_ev_investment
        )
        
        # Calculate when cumulative profit turns positive (actual breakeven)
        cumulative_profits = monthly_projections['cumulative_profit']
        break_even_month_actual = None
        for i, profit in enumerate(cumulative_profits):
            if profit >= 0:
                break_even_month_actual = i + 1  # +1 because months start at 1
                break
        
        # ROI calculation
        total_3yr_profit = cumulative_profits[-1]
        roi_percentage = (total_3yr_profit / initial_ev_investment) * 100 if initial_ev_investment > 0 else 0
        
        return BusinessMetrics(
            total_turnover=base_revenue,
            net_revenue=net_revenue,
            total_costs=total_monthly_costs,
            gross_profit=gross_profit,
            profit_per_driver=profit_per_driver,
            break_even_rides=break_even_rides,
            break_even_month=break_even_month_actual,
            initial_investment=initial_ev_investment,
            roi_percentage=roi_percentage,
            total_3yr_profit=total_3yr_profit,
            ev_payback_months=break_even_month_actual,
            cost_breakdown=cost_breakdown,
            monthly_projections=monthly_projections
        )

# Initialize the calculator
calculator = RideShareEconomics()

# Sidebar Configuration
st.sidebar.header("🎛️ Configuration")

# Revenue & Driver Activity
st.sidebar.subheader("📈 Revenue & Driver Activity")
avg_ticket_size = st.sidebar.number_input("Average Ticket Size (₹)", min_value=1.0, value=80.0, step=1.0)
rides_per_day = st.sidebar.number_input("Average Rides per Day per Driver", min_value=1.0, value=20.0, step=1.0)
working_days = st.sidebar.number_input("Working Days per Month", min_value=1, value=26, step=1)
utilization_rate = st.sidebar.slider("Utilization Rate (%)", min_value=10, max_value=100, value=100, step=5)

# Driver Salary (applies to all models)
st.sidebar.subheader("💰 Driver Compensation")
driver_salary = st.sidebar.number_input("Monthly Salary per Driver (₹)", min_value=0.0, value=25000.0, step=1000.0)

# Aggregator Model Inputs
st.sidebar.subheader("🧑‍💼 Aggregator Model")
num_agg_drivers = st.sidebar.number_input("Number of Aggregator Drivers", min_value=0, value=100, step=1)
agg_driver_acquisition_cost = st.sidebar.number_input("Aggregator Driver Acquisition Cost (₹)", min_value=0.0, value=2000.0, step=100.0)

# Fleet Model Inputs
st.sidebar.subheader("🚗 Fleet Model")
num_fleet_drivers = st.sidebar.number_input("Number of Fleet Drivers", min_value=0, value=10, step=1)
fleet_driver_acquisition_cost = st.sidebar.number_input("Fleet Driver Acquisition Cost (₹)", min_value=0.0, value=5000.0, step=100.0)
ev_cost = st.sidebar.number_input("Cost of One EV (₹)", min_value=0.0, value=180000.0, step=5000.0)
ev_maintenance = st.sidebar.number_input("Monthly EV Maintenance/Insurance Cost (₹)", min_value=0.0, value=1500.0, step=100.0)
ev_fuel_cost = st.sidebar.number_input("Monthly Fuel/Mileage Cost per EV (₹)", min_value=0.0, value=4000.0, step=100.0)

# Common Parameters
st.sidebar.subheader("📊 Common Parameters")
driver_churn_rate = st.sidebar.slider("Driver Churn Rate (% per month)", min_value=0.0, max_value=50.0, value=10.0, step=0.5)
tax_rate = st.sidebar.slider("Tax Rate (%)", min_value=0.0, max_value=40.0, value=0.0, step=1.0)

# Fixed & Overhead Costs
st.sidebar.subheader("🏢 Fixed & Overhead Costs")
fixed_costs = st.sidebar.number_input("Monthly Fixed Costs (₹)", min_value=0.0, value=50000.0, step=1000.0)
agg_ops_salary = st.sidebar.number_input("Monthly Ops Team Salary (₹)", min_value=0.0, value=75000.0, step=1000.0)

# Prepare parameters dictionary
params = {
    'avg_ticket_size': avg_ticket_size,
    'rides_per_day': rides_per_day,
    'working_days': working_days,
    'utilization_rate': utilization_rate,
    'driver_salary': driver_salary,
    'num_agg_drivers': num_agg_drivers,
    'agg_driver_acquisition_cost': agg_driver_acquisition_cost,
    'agg_ops_salary': agg_ops_salary,
    'driver_churn_rate': driver_churn_rate,
    'num_fleet_drivers': num_fleet_drivers,
    'fleet_driver_acquisition_cost': fleet_driver_acquisition_cost,
    'ev_cost': ev_cost,
    'ev_maintenance': ev_maintenance,
    'ev_fuel_cost': ev_fuel_cost,
    'tax_rate': tax_rate,
    'fixed_costs': fixed_costs
}

# Calculate metrics for both models
aggregator_metrics = calculator.calculate_aggregator_model(params)
fleet_metrics = calculator.calculate_fleet_model(params)

# Main Dashboard
st.header("📊 Investment Analysis Dashboard")

st.subheader("💰 Return on Investment (3 Years)")
col1, col2 = st.columns(2)

with col1:
    profit_color = "#28a745" if aggregator_metrics.total_3yr_profit >= 0 else "#dc3545"
    st.markdown(f"""
    <div style="background-color: #f8f9fa; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #007bff;">
        <h3 style="color: #007bff; margin: 0;">🤝 Aggregator Model</h3>
        <p style="margin: 0.5rem 0;">Initial Investment: {format_currency(aggregator_metrics.initial_investment)}</p>
        <h2 style="color: {profit_color}; margin: 0.5rem 0;">Total Profit: {format_currency(aggregator_metrics.total_3yr_profit)}</h2>
        <p style="color: {profit_color}; margin: 0;">ROI: {aggregator_metrics.roi_percentage:.1f}%</p>
        <p style="margin: 0;">Breakeven: Month {aggregator_metrics.break_even_month if aggregator_metrics.break_even_month else 'N/A'}</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    profit_color = "#28a745" if fleet_metrics.total_3yr_profit >= 0 else "#dc3545"
    st.markdown(f"""
    <div style="background-color: #f8f9fa; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #6610f2;">
        <h3 style="color: #6610f2; margin: 0;">🛵 Fleet Model</h3>
        <p style="margin: 0.5rem 0;">Initial Investment: {format_currency(fleet_metrics.initial_investment)}</p>
        <h2 style="color: {profit_color}; margin: 0.5rem 0;">Total Profit: {format_currency(fleet_metrics.total_3yr_profit)}</h2>
        <p style="color: {profit_color}; margin: 0;">ROI: {fleet_metrics.roi_percentage:.1f}%</p>
        <p style="margin: 0;">Breakeven: Month {fleet_metrics.break_even_month if fleet_metrics.break_even_month else '∞'}</p>
    </div>
    """, unsafe_allow_html=True)
    
# Cumulative Profit Timeline with new colors
st.subheader("📊 Cumulative Profit Timeline")
months = list(range(1, 37))
agg_cumulative = aggregator_metrics.monthly_projections['cumulative_profit']
fleet_cumulative = fleet_metrics.monthly_projections['cumulative_profit']

fig_cumulative = go.Figure()
fig_cumulative.add_trace(go.Scatter(
    x=months, y=agg_cumulative, mode='lines+markers', 
    name='Aggregator', line=dict(color="#1f77b4", width=3)  # Blue color
))
fig_cumulative.add_trace(go.Scatter(
    x=months, y=fleet_cumulative, mode='lines+markers', 
    name='Fleet', line=dict(color="#9467bd", width=3)  # Purple color
))

# Add breakeven markers (keeping the dash style but with the new colors)
if aggregator_metrics.break_even_month:
    fig_cumulative.add_vline(x=aggregator_metrics.break_even_month, line_width=1, line_dash="dash", line_color="#1f77b4")
if fleet_metrics.break_even_month:
    fig_cumulative.add_vline(x=fleet_metrics.break_even_month, line_width=1, line_dash="dash", line_color="#9467bd")

fig_cumulative.update_layout(
    title='Cumulative Profit Over 36 Months', 
    xaxis_title='Month', 
    yaxis_title='Cumulative Profit (₹)',
    hovermode='x unified'
)
st.plotly_chart(fig_cumulative, use_container_width=True)

# Detailed Financials
st.subheader("📋 Detailed Financial Metrics")
tab1, tab2 = st.tabs(["Aggregator", "Fleet"])

with tab1:
    st.markdown(f"""
    #### Aggregator Model Details
    - **Monthly Turnover**: {format_currency(aggregator_metrics.total_turnover)}
    - **Monthly Net Revenue**: {format_currency(aggregator_metrics.net_revenue)}
    - **Monthly Costs**: {format_currency(aggregator_metrics.total_costs)}
    - **Monthly Profit per Driver**: {format_currency(aggregator_metrics.profit_per_driver)}
    - **Monthly Break-even Rides**: {aggregator_metrics.break_even_rides:,.0f} rides
    """)
    
    # Cost breakdown pie chart
    cost_df = pd.DataFrame({
        'Category': list(aggregator_metrics.cost_breakdown.keys()),
        'Amount': list(aggregator_metrics.cost_breakdown.values())
    })
    fig = px.pie(cost_df, names='Category', values='Amount', title='Monthly Cost Breakdown')
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown(f"""
    #### Fleet Model Details
    - **Initial Investment**: {format_currency(fleet_metrics.initial_investment)}
    - **Monthly Turnover**: {format_currency(fleet_metrics.total_turnover)}
    - **Monthly Net Revenue**: {format_currency(fleet_metrics.net_revenue)}
    - **Monthly Costs**: {format_currency(fleet_metrics.total_costs)}
    - **Monthly Profit per Driver**: {format_currency(fleet_metrics.profit_per_driver)}
    - **Monthly Break-even Rides**: {fleet_metrics.break_even_rides:,.0f} rides
    - **Payback Period**: {fleet_metrics.break_even_month if fleet_metrics.break_even_month else '∞'} months
    """)
    
    # Cost breakdown pie chart
    cost_df = pd.DataFrame({
        'Category': list(fleet_metrics.cost_breakdown.keys()),
        'Amount': list(fleet_metrics.cost_breakdown.values())
    })
    fig = px.pie(cost_df, names='Category', values='Amount', title='Monthly Cost Breakdown')
    st.plotly_chart(fig, use_container_width=True)

# Monthly Projections Table
st.subheader("📅 Monthly Financial Projections")
model_choice = st.selectbox("Select Model to View", ["Aggregator", "Fleet"])

if model_choice == "Aggregator":
    projections = aggregator_metrics.monthly_projections
else:
    projections = fleet_metrics.monthly_projections

projections_df = pd.DataFrame({
    'Month': projections['month'],
    'Turnover': [format_currency(x) for x in projections['total_turnover']],
    'Net Revenue': [format_currency(x) for x in projections['net_revenue']],
    'Costs': [format_currency(x) for x in projections['total_costs']],
    'Profit': [format_currency(x) for x in projections['gross_profit']],
    'Cumulative Profit': [format_currency(x) for x in projections['cumulative_profit']]
})

st.dataframe(projections_df, use_container_width=True, height=400)
