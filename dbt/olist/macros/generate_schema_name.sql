{#
    Use a model's custom schema name as-is (e.g. `marts`) instead of dbt's default
    `<target_schema>_<custom_schema>` (e.g. `staging_marts`).
    Models without a custom schema still land in the target schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
