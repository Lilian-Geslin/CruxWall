"""Logique métier de CruxWall : droits d'accès, quotas, limitation des tentatives, images, recherche, suppressions…

Un service ne connaît pas (ou presque pas) le détail des routes : les routes (src/routes) lisent la requête, appellent
les services puis répondent.
"""
