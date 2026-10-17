# Prompt

```
Using the olist data, build an interactive monthly performance dashboard as an artifact.

DATA
- Months from September 2016 to September 2018, month = month the order was placed. Exclude canceled and unavailable orders.
- Pull the data by month AND customer state (about 560 rows) as additive components: orders, revenue (total payment value), review score sum, review count, delivered orders, late orders. This lets the page recompute every metric for any state and period. Average review = sum / count, late % = late orders / delivered orders (orders with a delivery date).
- The SQL tool returns at most 200 rows per query, so fetch in month-range chunks and check that the state rows add up to the monthly totals before building. Expected overall: 98,207 orders and R$ 15,739,137.
- Include Nov 2016 as a zero-order month so the time axis has no gap.

LAYOUT (top to bottom)
1. Title "Olist Monthly Performance, Sep 2016 to Sep 2018", with an Auto / Light / Dark theme switch.
2. Filters: a State dropdown, period presets (All, 2017, 2018, Last 6 mo, Nov '17 – Mar '18), a "Show low-volume months" checkbox, and a Reset view button that appears when anything is changed.
3. Period selector: a small strip of monthly orders over the full timeline with a draggable window (drag either edge, slide the window, or draw a new one; arrow keys move a focused edge). The cards, all charts, the states list and the table recompute for the selected period.
4. Four summary cards: total orders, total revenue (BRL, formatted "R$ 15,739,137"), average review score, average late-delivery %. Each has a sparkline and a change against the period of equal length just before the selection, with an arrow and sign so color is never the only signal. A rising late % is shown as bad.
5. "Notable months" chips, shown only for all states, with matching ring markers on the charts. Compute the months and their text from the data (largest order jump, two highest late %, lowest review) instead of hard-coding them.
6. Chart 1: revenue as a line (left axis) with orders as bars (right axis). Keep the dual axis, with gridlines aligned so both scales read.
7. Chart 2: average review score as a line. Chart 3: late-delivery % as a line. End-value label on each.
8. Scatter of late % against review score, one dot per month sized by orders, with a trend line and the correlation r computed from the data.
9. States panel: ranking bars with a metric switcher (Orders, Revenue, Avg review, Late %), top 10 with a "show all" toggle. Clicking a state filters the whole dashboard. For review and late %, hide states with fewer than 100 reviewed or delivered orders in the period and say so.
10. Monthly numbers table: sortable, with revenue formatted as R$ with thousands separators and cents. A Copy CSV button copies the current view to the clipboard (artifact downloads are blocked, so show the CSV selected in a text box if the clipboard is refused).
11. Notes at the bottom, full width in two columns, covering definitions, how the cards are calculated, and the low-volume rule.

BEHAVIOR
- Hovering any trend chart shows one synced crosshair on all three, a tooltip with the month's four numbers, and highlights the table row. Clicking a chart point or table row pins that month (a strip under the cards shows it, with a Clear button).
- Summary card averages are the plain mean of the monthly values, leaving out Sep 2016 and Sep 2018 (1 to 2 orders each). Show the order-weighted figure on the line under each average.
- Any month with fewer than 30 orders (for the selected state) is a low-volume month. Leave it off the rate charts and the revenue line unless the checkbox is on. Always keep it in the table with a "low volume" tag.
- Remember the viewer's state, period, metric and theme in localStorage (wrapped in try/catch). Do not try to put state in the URL, because artifact pages only accept a plain #anchor.

DESIGN
- System sans-serif font, calm neutral surfaces, light and dark themes defined as tokens.
- One color per measure, used everywhere: revenue blue, orders orange, review aqua, late red. Validate the set with the dataviz palette validator in both themes.
- Thin marks: 2px lines, bars at most 24px wide with a rounded top, hairline gridlines, end dots at least 8px.
- Phone-friendly: no horizontal page scroll (the table scrolls inside its own container), cards stack to 2 columns then 1.

BEFORE PUBLISHING
- Check the script for errors, render it at desktop and phone width in both themes, and confirm the cards match the expected totals above.
```