# Grouping with aggregation

The MongoDB aggregation pipeline uses the group stage to combine input
documents by a shared expression. Set the group key to a field like category
and use a sum accumulator to calculate a total for each category. A match
stage before grouping can restrict which input documents participate.
