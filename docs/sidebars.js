/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    {
      type: 'link',
      label: 'Contents',
      href: '/',
    },
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/when-to-use',
        'getting-started/cookbook',
        'getting-started/basic-usage',
        'getting-started/performance',
        'getting-started/troubleshooting',
        'getting-started/migrating-to-2',
        'getting-started/best-practices',
      ],
    },
    {
      type: 'category',
      label: 'AI & agents',
      items: [
        'integrations/mcp',
        'integrations/ai',
        'integrations/sdk',
        'getting-started/cookbook',
        'commands/ai',
        'commands/doc',
        'commands/mcp',
        'use-cases/agents-and-mcp',
      ],
    },
    {
      type: 'category',
      label: 'Use Cases',
      items: [
        'use-cases/format-conversion',
        'use-cases/data-pipelines',
        'use-cases/quality-and-packaging',
        'use-cases/sql-and-analytics',
        'use-cases/agents-and-mcp',
      ],
    },
    {
      type: 'category',
      label: 'CLI Reference',
      items: [
        'commands/index',
        {
          type: 'category',
          label: 'Convert and I/O',
          items: [
            'commands/convert',
            'commands/repack',
            'commands/flatten',
            'commands/formats',
            'commands/shared-options',
            'commands/json-output',
          ],
        },
        {
          type: 'category',
          label: 'Inspect',
          collapsed: true,
          items: [
            'commands/analyze',
            'commands/headers',
            'commands/sniff',
            'commands/count',
            'commands/head',
            'commands/tail',
            'commands/table',
            'commands/stats',
            'commands/frequency',
            'commands/uniq',
          ],
        },
        {
          type: 'category',
          label: 'Transform',
          collapsed: true,
          items: [
            'commands/select',
            'commands/sort',
            'commands/sample',
            'commands/search',
            'commands/dedup',
            'commands/fill',
            'commands/rename',
            'commands/explode',
            'commands/replace',
            'commands/cat',
            'commands/join',
            'commands/diff',
            'commands/exclude',
            'commands/transpose',
            'commands/slice',
            'commands/fmt',
            'commands/split',
            'commands/enum',
            'commands/reverse',
            'commands/fixlengths',
            'commands/apply',
            'commands/mask',
          ],
        },
        {
          type: 'category',
          label: 'Quality',
          items: [
            'commands/validate',
            'commands/validate-rules',
            'commands/quality',
            'commands/schema',
            'commands/schema-bulk',
            'commands/schema-drift',
            'commands/doc',
          ],
        },
        {
          type: 'category',
          label: 'SQL and visualization',
          items: ['commands/sql', 'commands/plot'],
        },
        'commands/extract',
        {
          type: 'category',
          label: 'Packaging and pipelines',
          items: [
            'commands/package',
            'commands/pipeline',
            'commands/examples',
            'commands/migrate-script',
          ],
        },
        {
          type: 'category',
          label: 'Databases',
          items: ['commands/ingest', 'commands/db'],
        },
        {
          type: 'category',
          label: 'Interactive and API',
          items: ['commands/tui', 'commands/web', 'commands/api'],
        },
        {
          type: 'category',
          label: 'AI and agents',
          items: ['commands/ai', 'commands/mcp'],
        },
        {
          type: 'category',
          label: 'Extensibility',
          items: ['commands/plugins', 'commands/config'],
        },
      ],
    },
    {
      type: 'category',
      label: 'Data File Formats',
      items: ['formats/index'],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/sdk',
        'integrations/sdk-reference',
        'integrations/data-api',
        'integrations/cloud',
        'integrations/plugins',
        'integrations/mcp',
        'integrations/ai',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      items: [
        'development/contributing',
        'development/architecture',
        'development/testing',
        'development/benchmarks',
        'development/releasing',
        'development/error-handling',
        'development/community',
      ],
    },
    'license',
  ],
};

module.exports = sidebars;
