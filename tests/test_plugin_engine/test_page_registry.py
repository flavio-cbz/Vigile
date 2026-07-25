from __future__ import annotations

import pytest
from master.core.plugin_engine import PageRegistry
from master.core.plugin_manifest import ManifestPage

def test_page_registry_init():
    pr = PageRegistry()
    assert pr.get_all_pages() == []

def test_page_registry_register():
    pr = PageRegistry()
    pages = [
        ManifestPage(
            id="containers",
            title="Conteneurs",
            component="DockerContainers",
            sidebar=True,
            roles=["admin", "operator"]
        ),
        ManifestPage(
            id="detail",
            title="Détails",
            component="DockerContainerDetail",
            params=["containerId"],
            roles=["admin"]
        )
    ]
    pr.register("docker", [p.model_dump() for p in pages])
    
    all_pages = pr.get_all_pages()
    assert len(all_pages) == 2
    
    # Verify standard route building
    p1 = next(p for p in all_pages if p["id"] == "containers")
    assert p1["route"] == "/plugins/docker/containers"
    assert p1["plugin_id"] == "docker"
    
    # Verify parameter dynamic route building
    p2 = next(p for p in all_pages if p["id"] == "detail")
    assert p2["route"] == "/plugins/docker/detail/:containerId"

def test_page_registry_unregister():
    pr = PageRegistry()
    pages = [
        ManifestPage(id="p1", title="Page 1", component="C1")
    ]
    pr.register("test_p", [p.model_dump() for p in pages])
    assert len(pr.get_all_pages()) == 1
    
    pr.unregister("test_p")
    assert len(pr.get_all_pages()) == 0
