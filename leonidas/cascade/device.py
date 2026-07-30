"""Explicit local inference device selection."""


def resolve_device(requested: str) -> str:
  if requested not in ('auto', 'cuda', 'cpu'):
    raise ValueError(f'Unsupported device: {requested!r}')
  if requested == 'cpu':
    return 'cpu'
  try:
    import torch
  except ImportError as exc:
    if requested == 'cuda':
      raise RuntimeError('CUDA requested but PyTorch is unavailable') from exc
    return 'cpu'
  available = torch.cuda.is_available()
  if requested == 'cuda' and not available:
    raise RuntimeError('CUDA requested but torch.cuda.is_available() is false')
  return 'cuda' if available else 'cpu'
