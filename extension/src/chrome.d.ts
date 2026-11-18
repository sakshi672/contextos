declare namespace chrome {
  namespace storage {
    namespace local {
      function get(keys: string[]): Promise<Record<string, unknown>>
      function set(items: Record<string, unknown>): Promise<void>
      function remove(keys: string[]): Promise<void>
    }
  }
  namespace permissions {
    function request(request: { origins: string[] }): Promise<boolean>
  }
  namespace tabs {
    type Tab = { id?: number; windowId?: number; url?: string; title?: string }
    function query(query: { active: boolean; currentWindow: boolean }): Promise<Tab[]>
    function create(properties: { url: string }): Promise<Tab>
    function captureVisibleTab(windowId?: number, options?: { format: 'png' | 'jpeg'; quality?: number }): Promise<string>
  }
  namespace scripting {
    function executeScript<T>(injection: { target: { tabId: number }; func: () => T }): Promise<Array<{ result: T }>>
  }
}
