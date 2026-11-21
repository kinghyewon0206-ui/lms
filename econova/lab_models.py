"""Economics Lab models 3–9 (deterministic pure functions; no AI, no network).

public/static/js/econova-lab-models.js implements the same formulas with the same rounding, and
tests/test_lab_models.py checks that both give identical results. The two original simulations
(supply-demand, carbon-tax) stay in econova/simulations.py.

All numbers are hypothetical teaching values, not real statistics or forecasts.
Percent inputs and outputs are in percent points (2.5 means 2.5%).
"""
import math

from econova import grading
from econova.simulations import nice_max, r6

CALC_VERSION = "lab-1"


def _num(name, label, unit, lo, hi, step, default, integer=False):
    return {"name": name, "kind": "number", "label": label, "unit": unit, "min": lo, "max": hi, "step": step,
            "default": default, "integer": integer}


def _sel(name, label, options, default):
    return {"name": name, "kind": "select", "label": label, "options": options, "default": default}


PROJECTS = {
    # Hypothetical SDG projects for a city or school. Values are illustrative, not measured.
    "energy": {"label": "School energy efficiency (LED lighting and insulation)", "env_unit": "tonnes CO2e avoided per year",
               "values": {"investment": 120000, "op_cost": 2000, "benefit": 18000, "years": 15, "env_units": 60}},
    "food": {"label": "Cafeteria food waste reduction", "env_unit": "tonnes of food waste avoided per year",
             "values": {"investment": 25000, "op_cost": 6000, "benefit": 9500, "years": 8, "env_units": 12}},
    "water": {"label": "Water-saving fixtures and rainwater reuse", "env_unit": "thousand cubic metres of water saved per year",
              "values": {"investment": 60000, "op_cost": 1500, "benefit": 5000, "years": 20, "env_units": 9}},
    "transit": {"label": "More frequent bus service on one route", "env_unit": "tonnes CO2e avoided per year",
                "values": {"investment": 400000, "op_cost": 90000, "benefit": 115000, "years": 12, "env_units": 210}},
}

REDISTRIBUTION_MODES = [
    ["equal", "Equal payment to every household"],
    ["bottom_two", "Targeted to the two lowest-income households"],
    ["proportional", "In proportion to each household's pre-tax income"],
    ["top_two", "To the two highest-income households (regressive design)"],
]

SPECS = {
    "opportunity-cost": {
        "title": "Opportunity Cost & Resource Allocation", "course_id": "c01", "lesson_id": "c01-l2",
        "blurb": "Split a fixed budget between books and movie tickets. See which choices are affordable and what each one makes you give up.",
        "model_note": "Budget constraint: Px·X + Py·Y ≤ Budget. A budget constraint shows what one person can afford at given prices; it is not a production possibility frontier.",
        "inputs": [
            _num("budget", "Monthly budget", "$", 10, 500, 5, 120),
            _num("px", "Price of a book (good X)", "$ per book", 1, 50, 0.5, 12),
            _num("py", "Price of a movie ticket (good Y)", "$ per ticket", 1, 50, 0.5, 8),
            _num("x", "Books you choose", "books", 0, 40, 1, 4, True),
            _num("y", "Movie tickets you choose", "tickets", 0, 60, 1, 6, True),
        ],
        "presets": [
            {"label": "Starting plan", "values": {"budget": 120, "px": 12, "py": 8, "x": 4, "y": 6}},
            {"label": "Books get more expensive", "values": {"budget": 120, "px": 20, "py": 8, "x": 4, "y": 6}},
            {"label": "Budget cut", "values": {"budget": 80, "px": 12, "py": 8, "x": 4, "y": 6}},
            {"label": "Money left over", "values": {"budget": 120, "px": 12, "py": 8, "x": 3, "y": 4}},
        ],
        "rows": [["spending", "Total spending", "$"], ["leftover", "Money left over", "$"], ["over_budget", "Amount over budget", "$"],
                 ["max_x", "Most books affordable (no tickets)", "books"], ["max_y", "Most tickets affordable (no books)", "tickets"],
                 ["oc_x_in_y", "Opportunity cost of 1 book", "tickets"], ["oc_y_in_x", "Opportunity cost of 1 ticket", "books"],
                 ["forgone_y", "Tickets given up for your books", "tickets"], ["max_y_given_x", "Most tickets you could add to your books", "tickets"]],
        "assumptions": [
            "Prices stay the same however much you buy, and you can only buy whole items.",
            "Money you don't spend is simply left over; the model does not count saving it for later.",
            "Monetary cost is the dollars you pay. Opportunity cost is the next-best thing you give up: here, the tickets you could have bought with the same money.",
            "A budget constraint is about one buyer's spending. A production possibility frontier is about what an economy can produce with its resources; the two are different models.",
        ],
    },
    "inflation": {
        "title": "Inflation & Purchasing Power", "course_id": "c04", "lesson_id": "c04-l3",
        "blurb": "Grow a salary and the price level over time. Compare nominal income with what it can actually buy.",
        "model_note": "Price index P_t = 100·(1 + π)^t; nominal income Y_t = Y_0·(1 + g)^t; real income = Y_t ÷ (P_t / 100), in year-0 dollars.",
        "inputs": [
            _num("income0", "Starting annual income", "$", 1000, 200000, 1000, 40000),
            _num("inflation", "Inflation rate", "% per year", -5, 20, 0.1, 3),
            _num("wage_growth", "Nominal income growth", "% per year", -10, 20, 0.1, 2),
            _num("years", "Time period", "years", 1, 40, 1, 10, True),
            _num("basket0", "Price of a weekly grocery basket today", "$", 1, 1000, 1, 50),
        ],
        "presets": [
            {"label": "Pay rises slower than prices", "values": {"income0": 40000, "inflation": 3, "wage_growth": 2, "years": 10, "basket0": 50}},
            {"label": "Pay keeps up with prices", "values": {"income0": 40000, "inflation": 3, "wage_growth": 3, "years": 10, "basket0": 50}},
            {"label": "High inflation", "values": {"income0": 40000, "inflation": 12, "wage_growth": 6, "years": 10, "basket0": 50}},
            {"label": "Zero inflation", "values": {"income0": 40000, "inflation": 0, "wage_growth": 2, "years": 10, "basket0": 50}},
            {"label": "Falling prices (deflation)", "values": {"income0": 40000, "inflation": -2, "wage_growth": 0, "years": 10, "basket0": 50}},
        ],
        "rows": [["nominal_end", "Nominal income in the final year", "$"], ["real_end", "Real income in the final year (year-0 dollars)", "$"],
                 ["price_index_end", "Price index in the final year (year 0 = 100)", ""], ["basket_end", "Basket price in the final year", "$"],
                 ["baskets_start", "Baskets one year's income buys (year 0)", "baskets"], ["baskets_end", "Baskets one year's income buys (final year)", "baskets"],
                 ["nominal_change", "Total change in nominal income", "%"], ["real_change", "Total change in real income", "%"],
                 ["real_growth", "Real income growth per year (exact)", "%"], ["real_growth_approx", "Approximation: income growth − inflation", "percentage points"],
                 ["value_of_100", "What $100 of today's money buys in the final year, in today's prices", "$"]],
        "assumptions": [
            "Inflation and income growth are constant every year, and the grocery basket's price rises exactly with the overall price level.",
            "Real income is nominal income divided by the price index, so it is measured in the prices of year 0.",
            "The exact real growth rate is (1 + g) ÷ (1 + π) − 1. The shortcut g − π is close only when both rates are small.",
            "These are hypothetical paths, not forecasts. Real inflation varies from year to year and differs across households.",
        ],
    },
    "minimum-wage": {
        "title": "Labor Market & Minimum Wage", "course_id": "c05", "lesson_id": "c05-l3",
        "blurb": "Set a wage floor in a competitive labor market. See when it binds and how employment and job seekers change in the model.",
        "model_note": "Competitive labor market model: labor demand L_d = a − b·W, labor supply L_s = c + d·W (thousands of workers, W in $ per hour).",
        "inputs": [
            _num("a", "Labor demand at a wage of $0 (demand intercept a)", "thousand workers", 50, 1000, 5, 200),
            _num("b", "Drop in jobs offered per $1 higher wage (b)", "thousand workers per $1", 0.5, 50, 0.5, 8),
            _num("c", "Labor supply at a wage of $0 (supply intercept c; may be negative)", "thousand workers", -200, 500, 5, 20),
            _num("d", "Extra workers willing to work per $1 higher wage (d)", "thousand workers per $1", 0.5, 50, 0.5, 4),
            _num("wmin", "Minimum wage", "$ per hour", 0, 60, 0.25, 18),
        ],
        "presets": [
            {"label": "Binding minimum wage", "values": {"a": 200, "b": 8, "c": 20, "d": 4, "wmin": 18}},
            {"label": "Non-binding (below equilibrium)", "values": {"a": 200, "b": 8, "c": 20, "d": 4, "wmin": 12}},
            {"label": "Employers react little to wages", "values": {"a": 200, "b": 2, "c": 20, "d": 4, "wmin": 33}},
            {"label": "No minimum wage", "values": {"a": 200, "b": 8, "c": 20, "d": 4, "wmin": 0}},
        ],
        "rows": [["eq_wage", "Equilibrium wage (no minimum wage)", "$ per hour"], ["eq_employment", "Equilibrium employment", "thousand workers"],
                 ["wage", "Wage paid in the model", "$ per hour"], ["employment", "Employment in the model", "thousand workers"],
                 ["employment_change", "Change in employment", "thousand workers"], ["labor_supplied", "People who want to work at this wage", "thousand workers"],
                 ["excess_supply", "Job seekers who can't find work in the model", "thousand workers"],
                 ["wage_bill_before", "Total hourly pay without a minimum wage", "$ thousand per hour"], ["wage_bill", "Total hourly pay with the minimum wage", "$ thousand per hour"]],
        "assumptions": [
            "This is a competitive labor market model: many employers, none of whom can set wages on their own, and straight-line demand and supply.",
            "In this model, a minimum wage above the equilibrium wage lowers employment and creates excess labor supply. A minimum wage at or below equilibrium has no effect.",
            "Real labor markets can differ. When employers have wage-setting power (monopsony), economic theory predicts that a moderate minimum wage can raise both wages and employment. Empirical studies find a range of effects depending on the size of the increase and local conditions. This model does not show those cases.",
            "Excess supply counts people who want a job at the minimum wage but can't find one in the model. It is not the same as the official unemployment rate.",
        ],
    },
    "inequality": {
        "title": "Income Inequality & Redistribution", "course_id": "c06", "lesson_id": "c06-l2",
        "blurb": "Tax and transfer income among five fictional households. Watch the Lorenz curve and Gini coefficient respond, and see which designs reduce inequality.",
        "model_note": "Five fictional households, each standing for 20% of the population. Gini = Σ|y_i − y_j| ÷ (2·n²·mean income).",
        "inputs": [
            _num("h1", "Household 1 income", "$ thousand per year", 0, 300, 1, 12),
            _num("h2", "Household 2 income", "$ thousand per year", 0, 300, 1, 25),
            _num("h3", "Household 3 income", "$ thousand per year", 0, 300, 1, 40),
            _num("h4", "Household 4 income", "$ thousand per year", 0, 300, 1, 60),
            _num("h5", "Household 5 income", "$ thousand per year", 0, 300, 1, 113),
            _num("tax_rate", "Tax rate on income above the exemption", "%", 0, 60, 1, 20),
            _num("exemption", "Tax-free income (exemption)", "$ thousand", 0, 100, 1, 20),
            _sel("mode", "How the tax revenue is paid out", REDISTRIBUTION_MODES, "equal"),
        ],
        "presets": [
            {"label": "Progressive tax, equal payment", "values": {"h1": 12, "h2": 25, "h3": 40, "h4": 60, "h5": 113, "tax_rate": 20, "exemption": 20, "mode": "equal"}},
            {"label": "Targeted support", "values": {"h1": 12, "h2": 25, "h3": 40, "h4": 60, "h5": 113, "tax_rate": 20, "exemption": 20, "mode": "bottom_two"}},
            {"label": "Flat tax returned in proportion (no change)", "values": {"h1": 12, "h2": 25, "h3": 40, "h4": 60, "h5": 113, "tax_rate": 20, "exemption": 0, "mode": "proportional"}},
            {"label": "Regressive payout", "values": {"h1": 12, "h2": 25, "h3": 40, "h4": 60, "h5": 113, "tax_rate": 20, "exemption": 0, "mode": "top_two"}},
            {"label": "Equal incomes", "values": {"h1": 50, "h2": 50, "h3": 50, "h4": 50, "h5": 50, "tax_rate": 20, "exemption": 20, "mode": "equal"}},
        ],
        "rows": [["gini_before", "Gini coefficient before taxes and transfers", ""], ["gini_after", "Gini coefficient after taxes and transfers", ""],
                 ["gini_change", "Change in the Gini coefficient", ""], ["revenue", "Total tax revenue", "$ thousand"],
                 ["bottom_share_before", "Income share of the lowest-income household, before", "%"], ["bottom_share_after", "Income share of the lowest-income household, after", "%"],
                 ["top_share_before", "Income share of the highest-income household, before", "%"], ["top_share_after", "Income share of the highest-income household, after", "%"],
                 ["ratio_before", "Top-to-bottom income ratio, before", "times"], ["ratio_after", "Top-to-bottom income ratio, after", "times"]],
        "assumptions": [
            "All data are fictional. Each household stands for one fifth of the population.",
            "All tax revenue is paid back out, so total income stays the same. The model ignores administration costs and assumes nobody changes how much they work or earn because of the tax.",
            "With only five groups, the Gini coefficient can range from 0 (everyone equal) to 0.8 (one household has everything). Official Gini coefficients use many more households.",
            "Whether a policy reduces inequality depends on its design: who pays the tax and who receives the money.",
        ],
    },
    "compound-interest": {
        "title": "Savings, Compound Interest & Debt", "course_id": "c07", "lesson_id": "c07-l2",
        "blurb": "Build savings with monthly deposits and compound interest, then compare with paying down a loan.",
        "model_note": "Savings: deposits at the end of each month, interest at APR r compounded n times a year (equivalent monthly rate (1 + r/n)^(n/12) − 1). Loan: monthly rate = loan APR ÷ 12.",
        "inputs": [
            _num("principal", "Starting savings", "$", 0, 100000, 100, 1000),
            _num("monthly", "Monthly deposit", "$ per month", 0, 2000, 10, 100),
            _num("rate", "Savings interest rate (APR)", "% per year", 0, 15, 0.1, 4),
            _sel("compounding", "Compounding frequency", [[1, "Yearly"], [4, "Quarterly"], [12, "Monthly"], [365, "Daily"]], 12),
            _num("years", "Saving period", "years", 1, 50, 1, 20, True),
            _num("inflation", "Inflation rate", "% per year", -2, 10, 0.1, 2.5),
            _num("loan", "Loan amount", "$", 0, 100000, 100, 10000),
            _num("loan_apr", "Loan interest rate (APR)", "% per year", 0, 36, 0.1, 7),
            _num("payment", "Monthly loan payment", "$ per month", 0, 5000, 5, 200),
        ],
        "groups": [["Savings plan", ["principal", "monthly", "rate", "compounding", "years", "inflation"]],
                   ["Borrowing scenario (separate)", ["loan", "loan_apr", "payment"]]],
        "presets": [
            {"label": "Steady saver", "values": {"principal": 1000, "monthly": 100, "rate": 4, "compounding": 12, "years": 20, "inflation": 2.5, "loan": 10000, "loan_apr": 7, "payment": 200}},
            {"label": "Zero interest", "values": {"principal": 1000, "monthly": 100, "rate": 0, "compounding": 12, "years": 20, "inflation": 2.5, "loan": 10000, "loan_apr": 7, "payment": 200}},
            {"label": "Interest below inflation", "values": {"principal": 5000, "monthly": 0, "rate": 1, "compounding": 12, "years": 20, "inflation": 3, "loan": 10000, "loan_apr": 7, "payment": 200}},
            {"label": "Credit card debt, small payments", "values": {"principal": 1000, "monthly": 100, "rate": 4, "compounding": 12, "years": 20, "inflation": 2.5, "loan": 5000, "loan_apr": 24, "payment": 110}},
        ],
        "rows": [["balance_end", "Savings balance at the end", "$"], ["contributions_end", "Total you deposited", "$"], ["interest_end", "Interest earned", "$"],
                 ["real_balance_end", "Balance in today's prices (after inflation)", "$"], ["apy", "Annual percentage yield (APY)", "%"],
                 ["real_return", "Real return per year (after inflation)", "%"],
                 ["loan_months", "Months to repay the loan", "months"], ["loan_total_paid", "Total loan payments", "$"],
                 ["loan_total_interest", "Total interest paid on the loan", "$"], ["loan_ear", "Loan cost as an effective annual rate", "%"],
                 ["loan_first_interest", "Interest charged in the first month", "$"]],
        "assumptions": [
            "The interest rate, deposits and inflation stay the same every year, and there are no fees or taxes. Real savings accounts and investments can earn different or variable returns; nothing here is guaranteed.",
            "APR is the yearly rate before compounding. APY is what you actually earn in a year once interest is added n times: APY = (1 + APR ÷ n)^n − 1.",
            "When interest is credited less often than monthly, the model uses the equivalent monthly rate, so deposits made during the year earn interest from the month they are made.",
            "The loan charges APR ÷ 12 each month on the remaining balance. If the payment does not cover the first month's interest, the debt never shrinks.",
        ],
    },
    "comparative-advantage": {
        "title": "International Trade & Comparative Advantage", "course_id": "c08", "lesson_id": "c08-l1",
        "blurb": "Two countries, two goods. Change productivity and the terms of trade to find when specialization and trade benefit both sides.",
        "model_note": "Each country has a fixed number of labor hours. Producing one unit takes a fixed number of hours, so each production possibility frontier is a straight line.",
        "inputs": [
            _num("a_food", "Hours to make 1 unit of food in Alba", "hours", 0.5, 20, 0.5, 1),
            _num("a_cloth", "Hours to make 1 unit of cloth in Alba", "hours", 0.5, 20, 0.5, 2),
            _num("b_food", "Hours to make 1 unit of food in Boren", "hours", 0.5, 20, 0.5, 4),
            _num("b_cloth", "Hours to make 1 unit of cloth in Boren", "hours", 0.5, 20, 0.5, 2),
            _num("labor_a", "Labor hours available in Alba", "hours", 10, 500, 10, 100),
            _num("labor_b", "Labor hours available in Boren", "hours", 10, 500, 10, 200),
            _num("share_a", "Alba's labor on food before trade", "%", 0, 100, 5, 50),
            _num("share_b", "Boren's labor on food before trade", "%", 0, 100, 5, 50),
            _num("price", "Terms of trade (units of cloth per unit of food)", "cloth per food", 0.1, 10, 0.05, 1),
            _num("exported", "Food sold by the food-exporting country", "units of food", 0, 500, 1, 35),
        ],
        "groups": [["Productivity (unit labor requirements)", ["a_food", "a_cloth", "b_food", "b_cloth"]],
                   ["Resources and production before trade", ["labor_a", "labor_b", "share_a", "share_b"]],
                   ["Trade deal", ["price", "exported"]]],
        "presets": [
            {"label": "Mutual gains", "values": {"a_food": 1, "a_cloth": 2, "b_food": 4, "b_cloth": 2, "labor_a": 100, "labor_b": 200, "share_a": 50, "share_b": 50, "price": 1, "exported": 35}},
            {"label": "Alba better at both goods", "values": {"a_food": 1, "a_cloth": 2, "b_food": 6, "b_cloth": 3, "labor_a": 100, "labor_b": 300, "share_a": 50, "share_b": 50, "price": 1, "exported": 30}},
            {"label": "Terms outside the gain range", "values": {"a_food": 1, "a_cloth": 2, "b_food": 4, "b_cloth": 2, "labor_a": 100, "labor_b": 200, "share_a": 50, "share_b": 50, "price": 3, "exported": 20}},
            {"label": "No comparative advantage", "values": {"a_food": 1, "a_cloth": 2, "b_food": 2, "b_cloth": 4, "labor_a": 100, "labor_b": 200, "share_a": 50, "share_b": 50, "price": 0.5, "exported": 20}},
        ],
        "rows": [["oc_a", "Alba: opportunity cost of 1 food", "cloth"], ["oc_b", "Boren: opportunity cost of 1 food", "cloth"],
                 ["autarky_food_a", "Alba before trade: food", "units"], ["autarky_cloth_a", "Alba before trade: cloth", "units"],
                 ["autarky_food_b", "Boren before trade: food", "units"], ["autarky_cloth_b", "Boren before trade: cloth", "units"],
                 ["cons_food_a", "Alba with trade: food", "units"], ["cons_cloth_a", "Alba with trade: cloth", "units"],
                 ["cons_food_b", "Boren with trade: food", "units"], ["cons_cloth_b", "Boren with trade: cloth", "units"],
                 ["world_food_before", "World food output before trade", "units"], ["world_food_after", "World food output with specialization", "units"],
                 ["world_cloth_before", "World cloth output before trade", "units"], ["world_cloth_after", "World cloth output with specialization", "units"]],
        "assumptions": [
            "Labor is the only input, each hour is equally productive within a country, and opportunity costs are constant (straight-line frontiers).",
            "With trade, each country specializes completely in the good it has a comparative advantage in. There are no transport costs or tariffs.",
            "Both countries gain only if the terms of trade lie strictly between their opportunity costs. At other terms, at least one side is no better off and would not agree.",
            "Gains are measured against each country's own frontier. Whether a country ends up with more of both goods also depends on how much it trades.",
            "Alba and Boren are fictional. Real trade also affects different groups within a country differently, which this model does not show.",
        ],
    },
    "sdg-project": {
        "title": "SDG Policy Evaluation", "course_id": "c09", "lesson_id": "c09-l2",
        "blurb": "Evaluate a hypothetical sustainability project with cash flows, discounting and net present value, and compare it with alternatives.",
        "model_note": "Net present value: NPV = −I + Σ (B − C) ÷ (1 + r)^t for t = 1 … N. Environmental benefits are reported separately unless you give them a money value.",
        "inputs": [
            _sel("project", "Project", [[k, v["label"]] for k, v in PROJECTS.items()], "energy"),
            _num("investment", "Upfront investment (year 0)", "$", 0, 2000000, 1000, 120000),
            _num("op_cost", "Annual operating cost", "$ per year", 0, 200000, 500, 2000),
            _num("benefit", "Annual money benefit (savings or revenue)", "$ per year", 0, 500000, 500, 18000),
            _num("years", "Project life", "years", 1, 40, 1, 15, True),
            _num("discount", "Discount rate", "% per year", 0, 15, 0.1, 4),
            _num("env_units", "Environmental benefit per year (see the project's unit)", "units per year", 0, 100000, 1, 60),
            _num("env_value", "Optional money value per unit of environmental benefit (assumed)", "$ per unit", 0, 1000, 1, 0),
        ],
        "presets": [{"label": v["label"], "values": {"project": k, **v["values"], "discount": 4, "env_value": 0}} for k, v in PROJECTS.items()],
        "rows": [["npv", "Net present value (money only)", "$"], ["npv_with_env", "NPV including the valued environmental benefit", "$"],
                 ["pv_benefits", "Present value of benefits", "$"], ["pv_costs", "Present value of costs (investment + operating)", "$"],
                 ["bcr", "Benefit-cost ratio", ""], ["payback", "Payback period (undiscounted)", "years"],
                 ["discounted_payback", "Payback period (discounted)", "years"], ["undiscounted_net", "Total net benefit without discounting", "$"],
                 ["env_total", "Total environmental benefit over the project life", "units"]],
        "assumptions": [
            "All projects and numbers are hypothetical. Costs and benefits are certain and the same every year, which real projects rarely are; try other values to test how sensitive the result is.",
            "Discounting converts future money into today's value: $1 received in t years is worth 1 ÷ (1 + r)^t today. A higher discount rate gives less weight to the future.",
            "Spending money on this project means it can't be used for something else: that is its opportunity cost, which the discount rate partly represents.",
            "Environmental benefits are measured in physical units. Putting a money value on them is a judgment, so the model shows NPV with and without that value.",
        ],
    },
}

ORDER = ("opportunity-cost", "inflation", "minimum-wage", "inequality", "compound-interest", "comparative-advantage", "sdg-project")


class LabError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def input_names(sim_id):
    return tuple(i["name"] for i in SPECS[sim_id]["inputs"])


def defaults(sim_id):
    return {i["name"]: i["default"] for i in SPECS[sim_id]["inputs"]}


def parse_inputs(sim_id, raw):
    if sim_id not in SPECS:
        raise LabError("simulation", "Unknown simulation.")
    out = {}
    for spec in SPECS[sim_id]["inputs"]:
        name, value = spec["name"], raw.get(spec["name"], "")
        if spec["kind"] == "select":
            for opt_value, _label in spec["options"]:
                if str(opt_value) == str(value).strip():
                    out[name] = opt_value
                    break
            else:
                raise LabError(name, f"{spec['label']}: choose one of the listed options.")
            continue
        if value is None or isinstance(value, bool):
            raise LabError(name, f"{spec['label']}: enter a number.")
        number = float(value) if isinstance(value, (int, float)) else grading.parse_number(str(value).strip())
        if number is None or not math.isfinite(number):
            raise LabError(name, f"{spec['label']}: enter a number.")
        if spec["integer"] and number != math.floor(number):
            raise LabError(name, f"{spec['label']}: enter a whole number.")
        if number < spec["min"] or number > spec["max"]:
            raise LabError(name, f"{spec['label']}: must be between {_fmt(spec['min'])} and {_fmt(spec['max'])}.")
        out[name] = number
    return out


# ------------------------------------------------------------------ LAB 01
def opportunity_cost(budget, px, py, x, y):
    spending = px * x + py * y
    leftover = budget - spending
    tol = 1e-9 * max(1.0, budget)
    status = "infeasible" if leftover < -tol else ("on_line" if abs(leftover) <= tol else "inside")
    return {"model": "opportunity-cost", "status": status,
            "spending": r6(spending), "leftover": r6(max(0.0, leftover)), "over_budget": r6(max(0.0, -leftover)),
            "max_x": r6(budget / px), "max_y": r6(budget / py), "oc_x_in_y": r6(px / py), "oc_y_in_x": r6(py / px),
            "forgone_y": r6(x * px / py), "max_y_given_x": r6(max(0.0, (budget - px * x) / py)),
            "x": r6(x), "y": r6(y)}


# ------------------------------------------------------------------ LAB 04
def inflation(income0, inflation, wage_growth, years, basket0):
    pi, g, n = inflation / 100.0, wage_growth / 100.0, int(years)
    series = []
    for t in range(n + 1):
        price_index = 100.0 * (1 + pi) ** t
        nominal = income0 * (1 + g) ** t
        series.append({"t": t, "nominal": r6(nominal), "real": r6(nominal / (price_index / 100.0)),
                       "price_index": r6(price_index), "basket": r6(basket0 * price_index / 100.0)})
    end = series[-1]
    nominal_end, real_end = income0 * (1 + g) ** n, income0 * (1 + g) ** n / (1 + pi) ** n
    real_growth = (1 + g) / (1 + pi) - 1
    status = "real_gain" if real_growth > 1e-12 else ("real_loss" if real_growth < -1e-12 else "real_flat")
    return {"model": "inflation", "status": status, "series": series,
            "nominal_end": end["nominal"], "real_end": end["real"], "price_index_end": end["price_index"], "basket_end": end["basket"],
            "baskets_start": r6(income0 / basket0), "baskets_end": r6(nominal_end / (basket0 * (1 + pi) ** n)),
            "nominal_change": r6((nominal_end / income0 - 1) * 100), "real_change": r6((real_end / income0 - 1) * 100),
            "real_growth": r6(real_growth * 100), "real_growth_approx": r6(wage_growth - inflation),
            "value_of_100": r6(100.0 / (1 + pi) ** n)}


# ------------------------------------------------------------------ LAB 05
def minimum_wage(a, b, c, d, wmin):
    base = {"model": "minimum-wage", "wmin": r6(wmin), "demand_choke_wage": r6(a / b)}
    if a <= c:
        return {**base, "status": "no_equilibrium",
                "reason": "Even at a wage of $0, more people want to work than employers want to hire, so there is no positive equilibrium wage."}
    w_eq = (a - c) / (b + d)
    l_eq = a - b * w_eq
    if l_eq <= 1e-12:
        return {**base, "status": "no_equilibrium", "reason": "Nobody would be employed at the equilibrium wage in this market."}
    out = {**base, "eq_wage": r6(w_eq), "eq_employment": r6(l_eq), "wage_bill_before": r6(w_eq * l_eq)}
    if wmin <= w_eq + 1e-12:
        return {**out, "status": "nonbinding", "wage": r6(w_eq), "employment": r6(l_eq), "employment_change": 0.0,
                "labor_supplied": r6(l_eq), "excess_supply": 0.0, "wage_bill": r6(w_eq * l_eq)}
    employment = max(0.0, a - b * wmin)
    supplied = c + d * wmin
    return {**out, "status": "binding" if employment > 0 else "binding_no_jobs", "wage": r6(wmin), "employment": r6(employment),
            "employment_change": r6(employment - l_eq), "labor_supplied": r6(supplied), "excess_supply": r6(supplied - employment),
            "wage_bill": r6(wmin * employment)}


# ------------------------------------------------------------------ LAB 06
def gini(values):
    """Gini of equally weighted groups: Σ_i Σ_j |y_i − y_j| ÷ (2·n²·mean). None if total income is 0."""
    n, total = len(values), sum(values)
    if total <= 0:
        return None
    diff = sum(abs(x - y) for x in values for y in values)
    return diff / (2 * n * total)


def lorenz(values):
    total, cum, pts = sum(values), 0.0, [{"p": 0.0, "s": 0.0}]   # p: population share, s: income share
    for i, v in enumerate(sorted(values)):
        cum += v
        pts.append({"p": r6((i + 1) / len(values)), "s": r6(cum / total)})
    return pts


def inequality(h1, h2, h3, h4, h5, tax_rate, exemption, mode):
    pre = [h1, h2, h3, h4, h5]
    total = sum(pre)
    if total <= 0:
        return {"model": "inequality", "status": "no_income", "reason": "Total income is 0, so income shares and the Gini coefficient are undefined."}
    tau = tax_rate / 100.0
    taxes = [tau * max(0.0, h - exemption) for h in pre]
    revenue = sum(taxes)
    rank = sorted(range(5), key=lambda i: (pre[i], i))
    transfers = [0.0] * 5
    if mode == "equal":
        transfers = [revenue / 5] * 5
    elif mode == "bottom_two":
        for i in rank[:2]:
            transfers[i] = revenue / 2
    elif mode == "top_two":
        for i in rank[-2:]:
            transfers[i] = revenue / 2
    else:   # proportional
        transfers = [revenue * h / total for h in pre]
    post = [pre[i] - taxes[i] + transfers[i] for i in range(5)]
    g0, g1 = gini(pre), gini(post)
    lo0, hi0, lo1, hi1 = min(pre), max(pre), min(post), max(post)
    change = g1 - g0
    status = "less_equal" if change > 1e-9 else ("more_equal" if change < -1e-9 else "unchanged")
    return {"model": "inequality", "status": status, "pre": [r6(v) for v in pre], "post": [r6(v) for v in post],
            "taxes": [r6(v) for v in taxes], "transfers": [r6(v) for v in transfers], "revenue": r6(revenue),
            "gini_before": r6(g0), "gini_after": r6(g1), "gini_change": r6(change),
            "lorenz_before": lorenz(pre), "lorenz_after": lorenz(post),
            "bottom_share_before": r6(lo0 / total * 100), "bottom_share_after": r6(lo1 / total * 100),
            "top_share_before": r6(hi0 / total * 100), "top_share_after": r6(hi1 / total * 100),
            "ratio_before": r6(hi0 / lo0) if lo0 > 0 else None, "ratio_after": r6(hi1 / lo1) if lo1 > 0 else None}


# ------------------------------------------------------------------ LAB 07
MAX_LOAN_MONTHS = 600


def compound_interest(principal, monthly, rate, compounding, years, inflation, loan, loan_apr, payment):
    r, n, pi, T = rate / 100.0, int(compounding), inflation / 100.0, int(years)
    i = (1 + r / n) ** (n / 12.0) - 1
    bal, series = principal, []
    for t in range(T + 1):
        if t > 0:
            for _ in range(12):
                bal = bal * (1 + i) + monthly
        contrib = principal + 12 * monthly * t
        series.append({"t": t, "balance": r6(bal), "contributions": r6(contrib), "interest": r6(bal - contrib),
                       "real": r6(bal / (1 + pi) ** t)})
    apy = (1 + r / n) ** n - 1
    end = series[-1]
    out = {"model": "compound-interest", "series": series, "balance_end": end["balance"], "contributions_end": end["contributions"],
           "interest_end": end["interest"], "real_balance_end": end["real"], "apy": r6(apy * 100),
           "real_return": r6(((1 + apy) / (1 + pi) - 1) * 100), "monthly_rate": r6(i * 100)}
    j = loan_apr / 100.0 / 12
    loan_series = [{"t": 0, "balance": r6(loan)}]
    out.update(loan_ear=r6(((1 + j) ** 12 - 1) * 100), loan_first_interest=r6(loan * j))
    if loan <= 0:
        out.update(loan_status="no_loan", loan_series=loan_series)
        return {**out, "status": "ok"}
    if payment <= loan * j + 1e-12:
        out.update(loan_status="never_repaid", loan_series=loan_series)
        return {**out, "status": "ok"}
    lb, paid, interest_paid, months = loan, 0.0, 0.0, 0
    while lb > 1e-9 and months < MAX_LOAN_MONTHS:
        interest = lb * j
        pay = min(payment, lb + interest)
        lb = lb + interest - pay
        paid += pay
        interest_paid += interest
        months += 1
        if months % 12 == 0 or lb <= 1e-9:
            loan_series.append({"t": r6(months / 12.0), "balance": r6(max(0.0, lb))})
    out.update(loan_series=loan_series, loan_total_paid=r6(paid), loan_total_interest=r6(interest_paid))
    if lb > 1e-9:
        out.update(loan_status="not_repaid_in_50_years", loan_remaining=r6(lb))
    else:
        out.update(loan_status="repaid", loan_months=months)
    return {**out, "status": "ok"}


# ------------------------------------------------------------------ LAB 08
def comparative_advantage(a_food, a_cloth, b_food, b_cloth, labor_a, labor_b, share_a, share_b, price, exported):
    sa, sb = share_a / 100.0, share_b / 100.0
    max_fa, max_ca, max_fb, max_cb = labor_a / a_food, labor_a / a_cloth, labor_b / b_food, labor_b / b_cloth
    oc_a, oc_b = a_food / a_cloth, b_food / b_cloth
    af, ac, bf, bc = sa * max_fa, (1 - sa) * max_ca, sb * max_fb, (1 - sb) * max_cb
    out = {"model": "comparative-advantage", "oc_a": r6(oc_a), "oc_b": r6(oc_b),
           "max_food_a": r6(max_fa), "max_cloth_a": r6(max_ca), "max_food_b": r6(max_fb), "max_cloth_b": r6(max_cb),
           "autarky_food_a": r6(af), "autarky_cloth_a": r6(ac), "autarky_food_b": r6(bf), "autarky_cloth_b": r6(bc),
           "world_food_before": r6(af + bf), "world_cloth_before": r6(ac + bc),
           "abs_food": "A" if a_food < b_food else ("B" if b_food < a_food else "none"),
           "abs_cloth": "A" if a_cloth < b_cloth else ("B" if b_cloth < a_cloth else "none")}
    if math.isclose(oc_a, oc_b, rel_tol=1e-12, abs_tol=1e-12):
        return {**out, "status": "no_comparative_advantage", "food_exporter": "none",
                "reason": "Both countries give up the same amount of cloth for one unit of food, so neither has a comparative advantage. Specializing would not raise world output, so there are no gains from trade in this model."}
    exporter = "A" if oc_a < oc_b else "B"
    if exporter == "A":
        food, cloth, oc_exp, oc_imp = max_fa, max_cb, oc_a, oc_b
    else:
        food, cloth, oc_exp, oc_imp = max_fb, max_ca, oc_b, oc_a
    out.update(food_exporter=exporter, world_food_after=r6(food), world_cloth_after=r6(cloth),
               gain_range_low=r6(oc_exp), gain_range_high=r6(oc_imp))
    if exported > food + 1e-9 or price * exported > cloth + 1e-9:
        return {**out, "status": "infeasible_trade",
                "reason": "The trade is impossible: the exporter can't sell more food than it makes, and the other country can't pay with more cloth than it makes."}
    exp_bundle, imp_bundle = (food - exported, price * exported), (exported, cloth - price * exported)
    cons_a, cons_b = (exp_bundle, imp_bundle) if exporter == "A" else (imp_bundle, exp_bundle)
    reach_a = cons_a[0] / max_fa + cons_a[1] / max_ca   # > 1: beyond Alba's own frontier
    reach_b = cons_b[0] / max_fb + cons_b[1] / max_cb
    out.update(cons_food_a=r6(cons_a[0]), cons_cloth_a=r6(cons_a[1]), cons_food_b=r6(cons_b[0]), cons_cloth_b=r6(cons_b[1]),
               reach_a=r6(reach_a), reach_b=r6(reach_b))
    if exported <= 1e-12:
        status = "no_trade"
    elif oc_exp + 1e-12 < price < oc_imp - 1e-12:
        status = "mutual_gain"
    elif math.isclose(price, oc_exp, rel_tol=1e-12, abs_tol=1e-12) or math.isclose(price, oc_imp, rel_tol=1e-12, abs_tol=1e-12):
        status = "one_side_no_gain"
    else:
        status = "one_side_loses"
    return {**out, "status": status}


# ------------------------------------------------------------------ LAB 09
def _project_npv(investment, op_cost, benefit, years, r, extra=0.0):
    npv = -investment
    for t in range(1, years + 1):
        npv += (benefit - op_cost + extra) / (1 + r) ** t
    return npv


def _payback(flows):
    """First time (in years, interpolated within the year) when cumulative flows reach 0. None if never."""
    cum = flows[0]
    if cum >= 0:
        return 0.0
    for t in range(1, len(flows)):
        if cum + flows[t] >= 0 and flows[t] > 0:
            return (t - 1) + (-cum) / flows[t]
        cum += flows[t]
    return None


def sdg_project(project, investment, op_cost, benefit, years, discount, env_units, env_value):
    r, n = discount / 100.0, int(years)
    net = benefit - op_cost
    flows, dflows, series, cum, dcum = [-investment], [-investment], [], -investment, -investment
    series.append({"t": 0, "cf": r6(-investment), "dcf": r6(-investment), "cum": r6(cum), "dcum": r6(dcum)})
    pv_b, pv_c = 0.0, investment
    for t in range(1, n + 1):
        df = 1 / (1 + r) ** t
        flows.append(net)
        dflows.append(net * df)
        cum += net
        dcum += net * df
        pv_b += benefit * df
        pv_c += op_cost * df
        series.append({"t": t, "cf": r6(net), "dcf": r6(net * df), "cum": r6(cum), "dcum": r6(dcum)})
    npv = dcum
    payback, dpayback = _payback(flows), _payback(dflows)
    out = {"model": "sdg-project", "series": series, "npv": r6(npv), "pv_benefits": r6(pv_b), "pv_costs": r6(pv_c),
           "bcr": r6(pv_b / pv_c) if pv_c > 0 else None, "payback": r6(payback) if payback is not None else None,
           "discounted_payback": r6(dpayback) if dpayback is not None else None, "undiscounted_net": r6(cum),
           "env_total": r6(env_units * n), "env_unit": PROJECTS[project]["env_unit"],
           "status": "npv_positive" if npv > 1e-6 else ("npv_negative" if npv < -1e-6 else "npv_zero")}
    if env_value > 0:
        out["npv_with_env"] = r6(_project_npv(investment, op_cost, benefit, n, r, env_units * env_value))
    out["alternatives"] = [{"project": k, "label": v["label"],
                            "npv": r6(_project_npv(v["values"]["investment"], v["values"]["op_cost"], v["values"]["benefit"],
                                                   v["values"]["years"], r))}
                           for k, v in PROJECTS.items()]
    return out


FUNCS = {"opportunity-cost": opportunity_cost, "inflation": inflation, "minimum-wage": minimum_wage, "inequality": inequality,
         "compound-interest": compound_interest, "comparative-advantage": comparative_advantage, "sdg-project": sdg_project}


def run(sim_id, raw):
    inputs = parse_inputs(sim_id, raw)
    return inputs, FUNCS[sim_id](**inputs)


def result_rows(sim_id, results):
    return [(label, results[key], unit) for key, label, unit in SPECS[sim_id]["rows"]
            if isinstance(results.get(key), (int, float)) and not isinstance(results.get(key), bool)]


__all__ = ["SPECS", "ORDER", "CALC_VERSION", "LabError", "run", "parse_inputs", "defaults", "result_rows", "gini", "nice_max"]


# ------------------------------------------------------------------ Economics Lab catalog (all nine experiments)
COURSE_NAMES = {"c01": "Economics & Choices", "c02": "Markets & Prices", "c03": "Market Failure", "c04": "Growth & Stability",
                "c05": "Labor & Employment", "c06": "Inequality & Policy", "c07": "Personal Finance", "c08": "Global Economics",
                "c09": "SDG Economic Challenge"}
CLASSIC = {
    "supply-demand": {"title": "Supply & Demand", "course_id": "c02", "lesson_id": "c02-l1",
                      "blurb": "Shift demand and supply and watch the equilibrium price and quantity move. Compare a shift of a curve with a movement along it."},
    "carbon-tax": {"title": "Carbon Tax & Externalities", "course_id": "c03", "lesson_id": "c03-l3",
                   "blurb": "Add a per-unit carbon tax to a polluting market. Compare private and social costs and find the output that is efficient for society."},
}
LAB_ORDER = ("opportunity-cost", "supply-demand", "carbon-tax", "inflation", "minimum-wage", "inequality",
             "compound-interest", "comparative-advantage", "sdg-project")


def catalog():
    """The nine experiments in course order: id, title, course, lesson, short description, kind (classic | model)."""
    out = []
    for sid in LAB_ORDER:
        src, kind = (CLASSIC[sid], "classic") if sid in CLASSIC else (SPECS[sid], "model")
        out.append({"id": sid, "kind": kind, "title": src["title"], "course_id": src["course_id"],
                    "course_name": COURSE_NAMES[src["course_id"]], "lesson_id": src["lesson_id"], "blurb": src["blurb"]})
    return out


def for_course(course_id):
    return next((e for e in catalog() if e["course_id"] == course_id), None)
