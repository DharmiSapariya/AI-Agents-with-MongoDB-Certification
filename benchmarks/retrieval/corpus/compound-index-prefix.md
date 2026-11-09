# Compound index prefixes

A compound MongoDB index stores keys in field order. An index on customerId
followed by createdAt can support a query on customerId alone because that
field is the index prefix. Queries on createdAt alone cannot use the index
prefix. Choose the order based on the filter and sort patterns in the app.
